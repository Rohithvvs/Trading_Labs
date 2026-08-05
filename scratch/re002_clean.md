RE-002 Specification Package**.    
You can place this at the top of the combined document. It will help any LLM (or Speckit) navigate the specification easily.

---

# **RE-002 Specification Package**    
### Relative Strength Momentum Engine    
**Version:** 1.0    
**Status:** Ready for Review    
**Compliance:** REDS v1.0  

---

## **Index / Table of Contents**

### **Document 01 – Engine Foundation & Decision Architecture**  
1. Executive Summary    
2. Engine Mission    
3. Engine Philosophy    
4. Engine Scope (Included / Excluded)    
5. Engine Objectives    
6. Engine Inputs    
7. Engine Outputs    
8. Engine Invariants    
9. Market Participation Philosophy    
10. Success Criteria    
11. Engine Boundaries    
12. Out of Scope    
13. Document Status  

---

### **Document 02 – Strategy Architecture & Adaptive Strategy Orchestration**  
1. Purpose    
2. Strategy Philosophy    
3. Universe & Regime Filtering (RE-002 Specific)    
4. Strategy Architecture    
5. Primary Strategy Layer    
6. Supporting Strategy Layer    
7. Validation Layer    
8. Recommendation Layer    
9. Strategy Orchestration Model    
10. Strategy Prioritization    
11. Strategy Conflict Resolution    
12. Adaptive Behaviour by Market Regime    
13. Recommendation Generation Rules    
14. Explainability    
15. Engine-specific Overrides    
16. Out of Scope    
17. Document Status  

---

### **Document 03 – Technical Architecture & Data Specification**  
1. Purpose    
2. High-Level Technical Architecture    
3. Core Modules    
4. Data Flow    
5. Interfaces with Shared Core Services    
6. Recommendation Decision Object    
7. Logging & Audit Requirements    
8. Error Handling    
9. Performance & Determinism Requirements    
10. Out of Scope    
11. Document Status  

---

### **Document 04 – Validation, Testing & Experiment Framework**  
1. Purpose    
2. Validation Philosophy    
3. Validation Layers    
4. Historical Backtesting    
5. Walk-Forward Testing    
6. Paper Trading (Live Simulation)    
7. Performance Metrics (Mandatory)    
8. Experiment Evaluation Framework (EEF) Integration    
9. Promotion Criteria    
10. Rejection / Pause Criteria    
11. Experiment Tracking    
12. Reporting Requirements    
13. Out of Scope    
14. Document Status  

---

### **Document 05 – Deployment, Operations & Evolution**  
*(Not yet generated – will be added next)*

---

## **How to use this Index with an LLM**

When generating code or detailed design from this specification, you can instruct the LLM like this:

> “Using the RE-002 Specification Package, focus only on **Document 03 – Technical Architecture** and generate the module structure and data flow.”

or

> “Based on Document 02 and Document 04, generate the strategy prioritization logic and validation rules.”

---

Would you like me to now generate **RE-002 Document 05** so the full package becomes complete?  
Here is **RE-002 Document 01**.

---

# **RE-002 – Document 01**    
# **Engine Foundation & Decision Architecture**

### **Recommendation Engine Development Standard (REDS) v1.0 Compliant**

---

## **Document Information**

| Property                    | Value                                            |  
|----------------------------|--------------------------------------------------|  
| Engine ID                  | RE-002                                           |  
| Engine Name                | Relative Strength Momentum Engine                |  
| Version                    | 1.0                                              |  
| Status                     | Draft                                            |  
| Compliance                 | REDS v1.0                                        |  
| Target Market              | Indian Equity Cash Market                        |  
| Target Universe            | NIFTY500                                         |  
| Trading Style              | Long Only Swing Trading                          |  
| Architecture               | Inherits REDS v1.0                               |  
| Dependencies               | Trading Research Knowledge Base, Strategy Library, TLDM, REDS |

---

## **1. Executive Summary**

The **Relative Strength Momentum Engine (RE-002)** is designed to identify and recommend stocks that are demonstrating superior relative strength and leadership characteristics within the market.

Its core belief is that **market leaders tend to continue leading**, especially when supported by strong relative performance against the broader market and their sector peers.

RE-002 focuses on ranking, leadership, and momentum persistence rather than simple price trend continuation.

It inherits the complete Trading Lab architecture from REDS and only defines the relative-strength and leadership-specific decision philosophy.

---

## **2. Engine Mission**

The mission of RE-002 is:

> **Identify and recommend the strongest relative strength leaders in the market while adapting participation based on overall market regime and maintaining strict capital preservation discipline.**

The engine prioritizes:

- Leadership quality  
- Relative strength persistence  
- Capital preservation  
- Explainable decisions  
- Consistency across market regimes

---

## **3. Engine Philosophy**

### Philosophy 1 – Leaders Remain Leaders    
Stocks showing strong relative strength often continue to outperform, especially in trending markets.

### Philosophy 2 – Market Before Stock    
Overall market regime determines how aggressive or defensive the engine should be.

### Philosophy 3 – Relative Strength Before Absolute Price    
A stock’s performance relative to the market and its sector is more important than its absolute price trend alone.

### Philosophy 4 – Portfolio Before Trade    
Even a strong leader can be rejected if it increases overall portfolio risk.

### Philosophy 5 – Evidence Before Opinion    
Every recommendation must be supported by objective relative strength and leadership evidence.

---

## **4. Engine Scope**

### Included  
- Relative Strength ranking  
- Leadership identification  
- Sector strength confirmation  
- Momentum continuation of leaders  
- Multi-timeframe relative strength  
- Market regime adaptation  
- Portfolio-aware recommendations

### Excluded  
- Pure Mean Reversion  
- Event-driven / News-driven trades  
- Earnings gap strategies  
- Fundamental-first selection  
- Intraday trading  
- Short selling  
- Pure breakout strategies without relative strength confirmation

---

## **5. Engine Objectives**

1. Identify the strongest relative strength leaders    
2. Participate more aggressively in Bull markets    
3. Become highly selective in Sideways and Bear markets    
4. Produce explainable leadership-based recommendations    
5. Maintain consistent behavior across regimes    
6. Support paper trading and fair comparison with other engines    
7. Generate deterministic recommendation decisions  

---

## **6. Engine Inputs**

RE-002 consumes standardized inputs from Shared Core Services:

- Market Regime    
- Market Breadth    
- Sector Leadership / Sector Relative Strength    
- Stock Relative Strength    
- Liquidity Assessment    
- Portfolio State    
- Risk Policies    
- Strategy Metadata    
- Trading Objectives    
- Trading Styles  

---

## **7. Engine Outputs**

RE-002 produces the standard REDS Recommendation Decision Object with states:

- **BUY**  
- **WATCH**  
- **REJECT**

Each recommendation includes Strategy, Confidence, Evidence, Explanation, Risk Profile, and Portfolio Decision.

---

## **8. Engine Invariants**

### Business Invariants  
- Long-only swing trading    
- NIFTY500 universe    
- Market context before stock context    
- Relative Strength is a primary decision factor    
- Portfolio and Risk validation before final recommendation  

### Architectural Invariants  
- Must comply with REDS    
- Must consume Shared Core Services    
- Must produce the standard Recommendation Decision Object    
- Must integrate with Recommendation Orchestrator and EEF  

### Operational Invariants  
- Deterministic decisions    
- Full explainability    
- Complete audit trail    
- Version-controlled behavior  

---

## **9. Market Participation Philosophy**

### Bull Market  
- Higher participation    
- Focus on top relative strength leaders    
- Allow strong momentum continuation  

### Sideways Market  
- Significantly reduced participation    
- Only exceptional leaders with strong confirmation    
- Higher rejection rate  

### Bear Market  
- Minimal participation    
- Only the strongest relative strength survivors    
- Mostly WATCH or REJECT  

---

## **10. Success Criteria**

RE-002 is considered successful when it demonstrates:

- High quality of recommended leaders    
- Better relative performance of its BUY recommendations vs market    
- Capital preservation in weak markets    
- Consistent behavior across regimes    
- Positive paper trading results    
- Clear and explainable decisions  

Profit alone is not sufficient.

---

## **11. Engine Boundaries**

RE-002 is **not** responsible for:  
- Calculating base technical indicators (uses Shared Services)  
- Market regime detection  
- Portfolio optimization  
- Risk policy creation  
- Strategy research  
- Backtesting / Paper trading infrastructure  
- Production deployment

---

## **12. Out of Scope**

This document does not define:  
- Exact Relative Strength calculation formulas  
- Ranking algorithms  
- Specific indicator parameters  
- Technical architecture  
- Entry / Exit rules  
- Position sizing

These will be covered in later documents.

---

## **13. Document Status**

**RE-002 Document 01 Version:** 1.0    
**Status:** Ready for Review  

---

Would you like me to proceed with **RE-002 Document 02** next?

Here is **RE-002 Document 02**.

---

# **RE-002 – Document 02**    
# **Strategy Architecture & Adaptive Strategy Orchestration**

### **REDS v1.0 Compliant**

---

## **Document Information**

| Property          | Value                                                      |  
|-------------------|------------------------------------------------------------|  
| Engine            | RE-002                                                     |  
| Document          | 02                                                         |  
| Name              | Strategy Architecture & Adaptive Strategy Orchestration    |  
| Version           | 1.0                                                        |  
| Compliance        | REDS v1.0                                                  |  
| Dependencies      | RE-002 Document 01, REDS, Strategy Library, TLDM           |

---

## **1. Purpose**

This document defines the strategy orchestration model of RE-002.

It specifies:  
- Which strategy families belong to RE-002  
- How strategies are activated  
- How strategies cooperate and compete  
- How Relative Strength and Leadership are prioritized  
- How final recommendations are produced

This document does **not** define technical calculations or indicator formulas.

---

## **2. Strategy Philosophy**

RE-002 is **not** a single strategy.

It is a **leadership and relative strength orchestration engine**.

It answers one core question:

> **“Which stocks are currently demonstrating the strongest and most persistent relative strength leadership under the present market conditions?”**

---

## **3. Universe & Regime Filtering (RE-002 Specific)**

RE-002 follows the Shared Universe & Regime Filtering Standard from REDS and applies it as follows:

### Step 1: Market Regime Detection  
Reads current market regime (Bull / Sideways / Bear) from Market Regime Service.

### Step 2: Bull Stock Filter \+ Relative Strength Pre-Filter  
Only stocks that pass both conditions proceed:

- Basic Bull Stock conditions (Price > key moving averages)  
- Acceptable or strong Relative Strength vs market

Stocks with weak relative strength are rejected early.

### Step 3: Strategy Activation by Regime

| Market Regime | Behaviour in RE-002                              | Participation Level |  
|---------------|--------------------------------------------------|---------------------|  
| Bull          | Full leadership & momentum strategies            | High                |  
| Sideways      | Only exceptional relative strength leaders       | Low–Medium          |  
| Bear          | Only the strongest surviving leaders             | Very Low            |

---

## **4. Strategy Architecture**

RE-002 organizes strategies into four layers:

\`\`\`  
Relative Strength Momentum Engine  
        │  
        ▼  
Primary Strategy Layer  
        │  
        ▼  
Supporting Strategy Layer  
        │  
        ▼  
Validation Layer  
        │  
        ▼  
Recommendation Layer  
\`\`\`

---

## **5. Primary Strategy Layer**

Primary strategies generate candidate opportunities.

RE-002 primary strategy families:

- Relative Strength Leadership  
- Relative Strength Momentum Continuation  
- Sector Leadership Alignment  
- Strong RS \+ Trend Alignment

**Rule:** Only one primary strategy becomes the owner of any single recommendation.

---

## **6. Supporting Strategy Layer**

Supporting strategies never generate recommendations alone.    
They only add or reduce confidence.

Examples:  
- Multi-timeframe Relative Strength  
- Volume confirmation of leadership  
- Sector Relative Strength  
- Market Breadth support  
- Price structure quality

---

## **7. Validation Layer**

Validation can only reject or downgrade recommendations.

Includes:  
- Market Regime Validation  
- Liquidity Validation  
- Risk Validation  
- Portfolio Validation  
- Leadership Quality Validation

---

## **8. Recommendation Layer**

Combines:  
- Primary Strategy  
- Supporting Evidence  
- Validation Results

Produces one of:  
- **BUY**  
- **WATCH**  
- **REJECT**

---

## **9. Strategy Orchestration Model**

\`\`\`  
Market Context  
      ↓  
Market Regime Detection  
      ↓  
Bull Stock \+ Relative Strength Filter  
      ↓  
Determine Trading Objective  
      ↓  
Load Eligible Leadership Strategies  
      ↓  
Evaluate Candidates  
      ↓  
Apply Supporting Evidence  
      ↓  
Apply Validation Layer  
      ↓  
Rank by Relative Strength Quality  
      ↓  
Resolve Conflicts  
      ↓  
Generate Final Recommendation  
\`\`\`

---

## **10. Strategy Prioritization**

When multiple strategies qualify, priority is based on:

1. Strength of Relative Strength ranking  
2. Alignment with current market regime  
3. Sector leadership quality  
4. Persistence of outperformance  
5. Supporting evidence strength  
6. Overall confidence score

---

## **11. Strategy Conflict Resolution**

\`\`\`  
Relative Strength Quality  
      ↓  
Market Regime Alignment  
      ↓  
Strategy Priority  
      ↓  
Supporting Evidence  
      ↓  
Validation Results  
      ↓  
Confidence  
      ↓  
Primary Strategy Selected  
\`\`\`

Only one strategy owns the final recommendation.

---

## **12. Adaptive Behaviour by Market Regime**

### Bull Market  
- Higher number of leadership recommendations allowed  
- Strong RS \+ Momentum strategies preferred

### Sideways Market  
- Only top-tier relative strength leaders  
- Higher confirmation requirements  
- Many candidates moved to WATCH or REJECT

### Bear Market  
- Extremely selective  
- Only the strongest relative strength survivors  
- Most stocks rejected

---

## **13. Recommendation Generation Rules**

A BUY recommendation is generated only when:

- Stock has passed Bull Stock \+ Relative Strength filter  
- At least one primary leadership strategy qualifies  
- Supporting evidence is sufficient  
- Validation passes  
- Risk and Portfolio policies approve

Otherwise the result is WATCH or REJECT.

---

## **14. Explainability**

Every recommendation must record:

- Selected primary strategy  
- Relative Strength rank / score  
- Supporting evidence  
- Rejected alternative strategies  
- Validation results  
- Market Regime at decision time  
- Final rationale

---

## **15. Engine-specific Overrides**

RE-002 defines only relative strength and leadership specific behavior.

It does **not** override:  
- Shared Risk policies  
- Shared Portfolio policies  
- Shared Validation framework  
- Recommendation Decision Object  
- Shared Core Services

---

## **16. Out of Scope**

This document does not define:  
- Exact RS calculation formulas  
- Ranking algorithms  
- Indicator parameters  
- Technical implementation details  
- Entry/Exit execution rules

These belong to Document 03 and later.

---

## **17. Document Status**

**RE-002 Document 02 Version:** 1.0    
**Status:** Ready for Review  

---

Would you like me to continue with **RE-002 Document 03**?  
Here is **RE-002 Document 03**.

---

# **RE-002 – Document 03**    
# **Technical Architecture & Data Specification**

### **REDS v1.0 Compliant**

---

## **Document Information**

| Property          | Value                                                      |  
|-------------------|------------------------------------------------------------|  
| Engine            | RE-002                                                     |  
| Document          | 03                                                         |  
| Name              | Technical Architecture & Data Specification                |  
| Version           | 1.0                                                        |  
| Compliance        | REDS v1.0                                                  |  
| Dependencies      | RE-002 Document 01, Document 02, REDS, TLDM, Shared Core Services |

---

## **1. Purpose**

This document defines the technical architecture and data specifications of RE-002.

It covers:  
- Internal modules  
- Data flow  
- Interfaces with Shared Core Services  
- Feature generation focused on Relative Strength  
- Strategy execution sequence  
- Confidence scoring  
- Recommendation Decision Object population  
- Logging and error handling

This is a pure technical specification.    
It does not redefine business rules already defined in Documents 01 and 02.

---

## **2. High-Level Technical Architecture**

\`\`\`  
Market Data \+ Shared Core Services  
              │  
              ▼  
┌─────────────────────────────────────┐  
│         RE-002 Engine Core          │  
│                                     │  
│  1. Context Loader                  │  
│  2. Universe & RS Pre-Filter        │  
│  3. Strategy Orchestrator           │  
│  4. Feature Engine (RS focused)     │  
│  5. Strategy Evaluators             │  
│  6. Supporting Evidence Module      │  
│  7. Validation Engine               │  
│  8. Ranking & Conflict Resolver     │  
│  9. Confidence Scorer               │  
│ 10. Decision Builder                │  
│ 11. Explanation Generator           │  
└─────────────────────────────────────┘  
              │  
              ▼  
Recommendation Decision Object  
\`\`\`

---

## **3. Core Modules**

### 3.1 Context Loader  
Loads Market Regime, Breadth, Sector RS, Portfolio State, and Risk Policies from Shared Core Services.

### 3.2 Universe & Relative Strength Pre-Filter  
- Starts with NIFTY500  
- Applies Bull Stock Filter  
- Applies early Relative Strength filter  
- Rejects weak RS stocks before full evaluation

### 3.3 Strategy Orchestrator  
Determines which leadership strategies are eligible based on current Market Regime \+ Trading Objective.

### 3.4 Feature Engine (RS Focused)  
Generates features required by RE-002, with emphasis on:  
- Stock vs Market Relative Strength  
- Stock vs Sector Relative Strength  
- Multi-timeframe RS  
- RS persistence / slope  
- Leadership ranking features

### 3.5 Strategy Evaluators  
Each primary strategy has its own evaluator that returns candidate signals with raw scores and evidence.

### 3.6 Supporting Evidence Module  
Applies additional confirmation layers (Volume, Multi-timeframe, Sector strength, Breadth).

### 3.7 Validation Engine  
Runs Regime, Liquidity, Risk, Portfolio, and Leadership Quality validations.

### 3.8 Ranking & Conflict Resolver  
Ranks all valid candidates primarily by Relative Strength quality and selects one primary strategy per stock.

### 3.9 Confidence Scorer  
Calculates final Confidence Score using:  
- Relative Strength strength  
- Leadership quality  
- Supporting evidence  
- Regime alignment  
- Validation results

### 3.10 Decision Builder  
Constructs the standard Recommendation Decision Object (BUY / WATCH / REJECT).

### 3.11 Explanation Generator  
Produces clear human and machine readable explanation focused on why the stock is (or is not) a leader.

---

## **4. Data Flow**

\`\`\`  
Shared Core Services  
        │  
        ▼  
Context Loader  
        │  
        ▼  
Universe \+ RS Pre-Filter → Eligible Stocks  
        │  
        ▼  
Strategy Orchestrator → Active Leadership Strategies  
        │  
        ▼  
Feature Engine → RS & Leadership Features  
        │  
        ▼  
Strategy Evaluators → Candidate Signals  
        │  
        ▼  
Supporting Evidence → Enhanced Candidates  
        │  
        ▼  
Validation Engine → Validated Candidates  
        │  
        ▼  
Ranking & Conflict Resolver → Final Candidate  
        │  
        ▼  
Confidence Scorer → Scored Decision  
        │  
        ▼  
Decision Builder \+ Explanation Generator  
        │  
        ▼  
Recommendation Decision Object  
\`\`\`

---

## **5. Interfaces with Shared Core Services**

RE-002 consumes the following services (read-only):

| Service                        | Usage in RE-002                          |  
|--------------------------------|------------------------------------------|  
| SCS-01 Market Regime Service   | Regime detection & participation control |  
| SCS-02 Market Breadth Service  | Breadth confirmation                     |  
| SCS-03 Sector Analysis Service | Sector leadership                        |  
| SCS-04 Relative Strength Service | Core RS ranking & features             |  
| SCS-05 Liquidity Service       | Tradability filter                       |  
| SCS-06 Technical Indicator Service | Supporting technical features        |  
| SCS-08 Risk Service            | Risk validation                          |  
| SCS-09 Portfolio Service       | Portfolio validation                     |  
| SCS-10 Confidence Service      | Confidence framework                     |  
| SCS-11 Explainability Service  | Explanation templates                    |  
| SCS-12 Audit Service           | Decision logging                         |

RE-002 never re-implements these services.

---

## **6. Recommendation Decision Object**

RE-002 produces the standard REDS object containing:

- RecommendationID    
- EngineID \= RE-002    
- EngineVersion    
- MarketRegime    
- TradingObjective    
- TradingStyle    
- StrategyFamily    
- StrategyName    
- RecommendationState (BUY / WATCH / REJECT)    
- ConfidenceScore    
- RiskProfile    
- PortfolioDecision    
- Evidence (must include RS related evidence)    
- Explanation    
- Timestamp  

---

## **7. Logging & Audit Requirements**

Every decision must log:

- Input context (Regime, Breadth, etc.)  
- RS pre-filter results  
- Activated strategies  
- Candidate signals  
- Supporting evidence  
- Validation outcomes  
- Final ranking path  
- Confidence calculation  
- Full explanation

Logs must be deterministic and replayable.

---

## **8. Error Handling**

- If any critical Shared Core Service is unavailable → return empty result with error status  
- If RS features cannot be calculated for a stock → skip that stock  
- Prefer capital preservation (lean toward REJECT / WATCH) on conflicting signals

---

## **9. Performance & Determinism Requirements**

- Fully deterministic  
- Same inputs must produce same outputs  
- Designed for end-of-day batch execution  
- Must support full decision replay for research and audit

---

## **10. Out of Scope**

This document does not define:  
- Exact Relative Strength formulas  
- Ranking algorithm mathematics  
- Specific lookback periods  
- Database schema  
- API endpoint details  
- Frontend display logic

These will be defined in implementation or lower-level technical designs.

---

## **11. Document Status**

**RE-002 Document 03 Version:** 1.0    
**Status:** Ready for Review  

---

Would you like me to continue with **RE-002 Document 04**?

Here is **RE-002 Document 04**.

---

# **RE-002 – Document 04**    
# **Validation, Testing & Experiment Framework**

### **REDS v1.0 Compliant**

---

## **Document Information**

| Property          | Value                                                      |  
|-------------------|------------------------------------------------------------|  
| Engine            | RE-002                                                     |  
| Document          | 04                                                         |  
| Name              | Validation, Testing & Experiment Framework                 |  
| Version           | 1.0                                                        |  
| Compliance        | REDS v1.0                                                  |  
| Dependencies      | RE-002 Documents 01–03, REDS, Experiment Evaluation Framework (EEF) |

---

## **1. Purpose**

This document defines how RE-002 will be validated, tested, paper-traded, and evaluated.

It covers:  
- Historical validation methods  
- Walk-forward testing  
- Paper trading process  
- Performance metrics specific to Relative Strength leadership  
- Comparison rules against other engines  
- Promotion and rejection criteria  
- Experiment tracking

The goal is to ensure RE-002 is evaluated fairly and under real market conditions before any promotion decision.

---

## **2. Validation Philosophy**

RE-002 follows these principles:

- Profit alone is **not** sufficient  
- Quality of recommended leaders is more important than quantity  
- Consistency across market regimes is critical  
- Capital preservation in weak markets is a primary success measure  
- All engines must be evaluated using identical rules  
- Evaluation must be transparent, repeatable, and auditable

---

## **3. Validation Layers**

RE-002 must pass through the following layers in sequence:

\`\`\`  
1. Historical Backtesting  
        ↓  
2. Walk-Forward Testing  
        ↓  
3. Paper Trading (Live Simulation)  
        ↓  
4. Experiment Evaluation Framework (EEF)  
        ↓  
5. Promotion Review  
\`\`\`

No engine may skip any layer.

---

## **4. Historical Backtesting**

### Objectives  
- Test leadership and relative strength logic across multiple market regimes  
- Measure risk-adjusted performance of recommended leaders  
- Identify weaknesses in different market conditions

### Requirements  
- Use NIFTY500 universe  
- Include realistic transaction costs and slippage  
- Model circuit filters and liquidity constraints  
- Cover at least one full Bull, Bear, and Sideways cycle  
- Results must be fully reproducible

### Key Metrics to Record  
- Total Return  
- Maximum Drawdown  
- Profit Factor  
- Win Rate  
- Average Risk-Reward  
- Risk-Adjusted Return (Sharpe / Sortino or equivalent)  
- Performance by Market Regime  
- Average Relative Strength of BUY recommendations vs market

---

## **5. Walk-Forward Testing**

### Purpose  
To test robustness under changing market conditions and reduce overfitting risk.

### Method  
- Rolling or anchored walk-forward windows  
- Out-of-sample periods must never be used for parameter selection  
- Compare walk-forward results against pure historical backtest

### Success Criteria  
- Performance should not degrade dramatically out-of-sample  
- Drawdowns should remain controlled  
- Leadership quality should remain consistent with the engine’s philosophy

---

## **6. Paper Trading (Live Simulation)**

### Duration  
Minimum **3 months** of continuous paper trading (aligned with Trading Lab plan).

### Rules  
- All recommendations generated by RE-002 must be paper-traded  
- Same position sizing, risk, and portfolio rules as production  
- No discretionary overrides  
- Every trade must be logged with full decision context and explanation

### Tracking Requirements  
For every paper trade record:  
- Entry date & price  
- Exit date & price  
- Strategy used  
- Relative Strength rank / score at entry  
- Confidence score  
- Market regime at entry  
- Portfolio state at entry  
- Full explanation  
- Outcome metrics (P\&L, holding period, max adverse excursion, etc.)

---

## **7. Performance Metrics (Mandatory)**

### Return Metrics  
- Total Return  
- Annualized Return  
- Average Trade Return

### Risk Metrics  
- Maximum Drawdown  
- Average Drawdown  
- Volatility of returns  
- Risk-Adjusted Return

### Quality Metrics  
- Win Rate  
- Profit Factor  
- Average Risk-Reward Ratio  
- Expectancy

### Leadership-Specific Metrics  
- Average Relative Strength of BUY recommendations  
- Outperformance of recommended leaders vs NIFTY500  
- Persistence of leadership after recommendation  
- Percentage of recommendations that remain in top RS ranks

### Consistency Metrics  
- Performance in Bull markets  
- Performance in Bear markets  
- Performance in Sideways markets  
- Rolling performance stability

### Portfolio Metrics  
- Average Portfolio Heat  
- Maximum Concurrent Positions  
- Sector Concentration  
- Correlation of recommended stocks

---

## **8. Experiment Evaluation Framework (EEF) Integration**

RE-002 must fully integrate with the EEF.

The EEF will:  
- Collect results from all Recommendation Engines  
- Compare engines using identical metrics  
- Rank engines on risk-adjusted consistency and leadership quality  
- Track experiments over time  
- Support promotion / rejection decisions

RE-002 must expose all required metrics and trade logs in the standard EEF format.

---

## **9. Promotion Criteria**

RE-002 can be considered for promotion only if it meets **all** of the following:

1. Completes minimum 3 months of continuous paper trading  
2. Shows acceptable risk-adjusted performance  
3. Demonstrates capital preservation behavior in adverse regimes  
4. Shows consistent leadership quality across regimes  
5. Outperforms or matches peer engines on key consistency and leadership metrics  
6. Passes formal review by the Experiment Evaluation Framework  
7. Has complete audit trail and explainability

Promotion is **not** automatic.

---

## **10. Rejection / Pause Criteria**

RE-002 should be paused or rejected if:

- Maximum Drawdown exceeds predefined risk limits  
- Leadership quality degrades significantly  
- Performance collapses across multiple regimes  
- The engine starts behaving inconsistently with its stated philosophy  
- Technical or data integrity issues persist

---

## **11. Experiment Tracking**

Every experiment involving RE-002 must record:

- Engine version  
- Strategy versions used  
- Time period  
- Market regimes covered  
- All performance metrics  
- Leadership quality metrics  
- Key observations and lessons learned  
- Decision (Continue / Improve / Promote / Reject)

Nothing is discarded.

---

## **12. Reporting Requirements**

During the paper trading phase, the following reports are required:

- Daily recommendation log  
- Weekly performance summary  
- Monthly full performance report  
- Regime-wise performance breakdown  
- Leadership quality report  
- Comparison report against other active engines

---

## **13. Out of Scope**

This document does not define:  
- Exact numerical thresholds for promotion (set by EEF policy)  
- Specific backtesting software or libraries  
- Database schema for trade logs  
- Visualization / dashboard design

---

## **14. Document Status**

**RE-002 Document 04 Version:** 1.0    
**Status:** Ready for Review  

---

Would you like me to continue with **RE-002 Document 05**?