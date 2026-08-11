import re

with open('D:/Trading_Labs/Trading_Labs/backend/app/agents/orchestrator_agent.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(
    '    ) -> ScreenerResponse:\n        if progress_callback:',
    '    ) -> tuple[ScreenerResponse, list, dict]:\n        if progress_callback:'
)

old_custom = '''            return await self._run_screener_stage(
                request=request,
                stage_name="Custom symbols",
                source_universe=request.symbols,
                duplicate_symbols_skipped=0,
                progress_callback=progress_callback,
            )'''
new_custom = '''            return (await self._run_screener_stage(
                request=request,
                stage_name="Custom symbols",
                source_universe=request.symbols,
                duplicate_symbols_skipped=0,
                progress_callback=progress_callback,
            ))[0]'''
code = code.replace(old_custom, new_custom)

old_stage_call = '''            stage_response = await self._run_screener_stage(
                request=request,
                stage_name=stage_name,
                source_universe=unique_symbols,
                duplicate_symbols_skipped=skipped,
                progress_callback=progress_callback,
            )
            scan_stages.extend(stage_response.scan_stages)'''
new_stage_call = '''            stage_response, s_res, s_frames = await self._run_screener_stage(
                request=request,
                stage_name=stage_name,
                source_universe=unique_symbols,
                duplicate_symbols_skipped=skipped,
                progress_callback=progress_callback,
            )
            all_screener_results.extend(s_res)
            all_prefetched_frames.update(s_frames)
            scan_stages.extend(stage_response.scan_stages)'''
code = code.replace(old_stage_call, new_stage_call)

lab_block_start_str = '        # Independent RE-001 / RE-002 evaluation over full data_valid universe.'
lab_block_end_str = '        # Release shared frames after both Production and lab paths have used them.'
start_idx = code.find(lab_block_start_str)
end_idx = code.find(lab_block_end_str, start_idx)

if start_idx != -1 and end_idx != -1:
    lab_block = code[start_idx:end_idx]
    code = code[:start_idx] + code[end_idx:]

code = code.replace('        return final_response\n\n    async def run_screener_dry_run', '        return final_response, screener_results, screener_frames\n\n    async def run_screener_dry_run')

# Also, insert initialization for all_screener_results etc in _run_screener_impl
init_vars = '''        if progress_callback:
            progress_callback({"stage": "Loading Market Universe...", "progress": 20, "heartbeat": True})
        self.logger.info("[SCAN] Loading universe...")
        universes = await self._prioritized_universes()
        self.logger.info(
            "[SCAN] Universe loaded | stages=%s | stage_list=%s",
            len(universes),
            ",".join(name for name, _ in universes),
        )

        all_screener_results = []
        all_prefetched_frames = {}
        master_universe = []
        master_seen = set()
        for stage_name, syms in universes:
            for s in syms:
                c = self._canonical_symbol(s)
                if c not in master_seen:
                    master_seen.add(c)
                    master_universe.append(s)
'''

code = code.replace(
'''        if progress_callback:
            progress_callback({"stage": "Loading Market Universe...", "progress": 20, "heartbeat": True})
        self.logger.info("[SCAN] Loading universe...")
        universes = await self._prioritized_universes()
        self.logger.info(
            "[SCAN] Universe loaded | stages=%s | stage_list=%s",
            len(universes),
            ",".join(name for name, _ in universes),
        )''', init_vars)

# Insert lab logic at the end of _run_screener_impl
end_of_impl = '''        self.logger.info(
            "Completed screener flow | scanned=%s | valid=%s | eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | duplicate_symbols_skipped=%s | stopped_at=%s",
            final_response.scanned_symbols,
            len(final_response.data_valid_symbols),
            len(final_response.eligible_symbols),
            len(final_response.matched_symbols),
            len(final_response.shortlisted_symbols),
            len(final_response.buy_candidate_symbols),
            len(final_response.watch_candidate_symbols),
            duplicate_symbols_skipped,
            stopped_at_stage,
        )'''

new_end = end_of_impl + '''

        # ---- Run Independent Lab Engines on FULL Master Universe ----
        if settings.is_re001_active() or settings.is_re002_active():
            screened_seen = {self._canonical_symbol(item.symbol) for item in all_screener_results}
            missing_symbols = [s for s in master_universe if self._canonical_symbol(s) not in screened_seen]
            if missing_symbols:
                self.logger.info("LAB_UNIVERSE | Backfilling %s missing symbols that Production skipped", len(missing_symbols))
                if progress_callback:
                    progress_callback({"stage": f"Lab: backfilling {len(missing_symbols)} missing symbols...", "progress": 85, "heartbeat": True})
                missing_results = await self.screener_service.screen_symbols_swing(
                    missing_symbols,
                    lookback_window=request.timeframe.lookback_window,
                    stage_name="Lab Backfill",
                    progress_callback=progress_callback,
                )
                all_screener_results.extend(missing_results)
                all_prefetched_frames.update(getattr(self.screener_service, "last_fetched_frames", {}))
            
            from ..services.independent_lab_universe import run_independent_lab_universe, build_lab_input_universe
            from ..services.re001.scan_context import get_scan_run_id
            
            data_valid_symbols = [
                item.symbol for item in all_screener_results
                if not item.conditions.get("data_source_failed", False) and not item.conditions.get("data_quality_failed", False)
            ]
            lab_input_audit = build_lab_input_universe(master_universe, data_valid_symbols)
            
            prod_recs = {}
            if final_response.analysis is not None:
                for item in final_response.analysis.items or []:
                    if getattr(item, "symbol", None) and getattr(item, "recommendation", None):
                        prod_recs[str(item.symbol)] = item.recommendation

            from ..services.scan_market_context import get_scan_market_regime
            _lab_market_regime = get_scan_market_regime()
            if _lab_market_regime is None and final_response.analysis is not None:
                for _item in final_response.analysis.items or []:
                    if getattr(_item, "market_regime", None) is not None:
                        _lab_market_regime = _item.market_regime
                        break
            
            lab_budget_s = 180.0
            try:
                from ..config.settings import settings as _scan_settings
                total_to = float(getattr(_scan_settings, "scan_execution_timeout_seconds", 600.0) or 600.0)
                lab_budget_s = max(60.0, min(240.0, total_to * 0.4))
            except Exception:
                pass
            
            lab_universe_summary = await run_independent_lab_universe(
                symbols=master_universe,
                lab_input_universe=lab_input_audit,
                screener_results=all_screener_results,
                prefetched_frames=all_prefetched_frames,
                market_regime=_lab_market_regime,
                mode=request.mode.value if hasattr(request.mode, "value") else str(request.mode),
                scan_run_id=get_scan_run_id(),
                production_recommendations=prod_recs or None,
                progress_callback=progress_callback,
                lookback_window=request.timeframe.lookback_window,
                max_duration_s=lab_budget_s,
                run_recommendation_backtest=False,
            )
            
            if final_response.analysis is not None and lab_universe_summary and lab_universe_summary.get("decisions"):
                decisions = lab_universe_summary["decisions"]
                merged_items = []
                for item in final_response.analysis.items or []:
                    eng = decisions.get(item.symbol) or decisions.get(self._canonical_symbol(item.symbol))
                    if eng:
                        try:
                            item = item.model_copy(update={"lab_engines": eng})
                        except Exception:
                            try:
                                object.__setattr__(item, "lab_engines", eng)
                            except Exception:
                                pass
                    merged_items.append(item)
                final_response.analysis = final_response.analysis.model_copy(update={"items": merged_items})
'''
code = code.replace(end_of_impl, new_end)

with open('D:/Trading_Labs/Trading_Labs/backend/patch_orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(code)
