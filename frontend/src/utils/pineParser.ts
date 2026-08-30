/**
 * Pine Script Lexer, AST Parser, Semantic Role Classifier, Variable Resolver, and Filter Normalizer.
 * Supports Pine Script v5 and v6.
 *
 * Core Principle:
 * - Only genuine ENTRY_FILTER conditions that decide whether to enter a new position become Builder filters.
 * - Runtime guards (VALIDITY_GUARD, POSITION_STATE, ORDER_CONTROL, ENTRY_BAR_PROTECTION, TRAILING_STOP_UPDATE)
 *   are classified as internal runtime conditions and NEVER become Builder filters or emit false warnings.
 * - Risk management (ATR, True Range, Trailing Stop, Ratchet) is separated from Entry filters.
 * - Exit conditions (Close < Trailing Stop) are isolated from enclosing position-management guards.
 * - Candidate ranking (Momentum 60) is classified as Ranking.
 * - Benchmark conditions (NIFTY 500 Close > SMA 50) are classified as Benchmark filters.
 */

export type ExpressionRole =
  | "ENTRY_FILTER"
  | "ENTRY_GUARD"
  | "EXIT_CONDITION"
  | "EXIT_GUARD"
  | "VALIDITY_GUARD"
  | "POSITION_STATE"
  | "ORDER_CONTROL"
  | "ENTRY_BAR_PROTECTION"
  | "TRAILING_STOP_UPDATE"
  | "RISK_MANAGEMENT"
  | "INDICATOR_DEFINITION"
  | "BENCHMARK_FILTER"
  | "RANKING"
  | "DISPLAY_ONLY"
  | "UNSUPPORTED";

export interface ModalBuilderFilter {
  id: string;
  field: string;
  period?: string;
  operator: string;
  rightKind: "literal" | "indicator";
  literal: string;
  indicator: string;
  indicatorPeriod: string;
  low: string;
  high: string;
  not?: boolean;
  role?: "ENTRY_FILTER" | "BENCHMARK_FILTER" | "EXIT_CONDITION";
  isBenchmark?: boolean;
  benchmarkSymbol?: string;
  label?: string;
}

export interface ParsedCondition {
  id: string;
  field: string;
  period?: string;
  operator: string;
  rightKind: "literal" | "indicator";
  literal: string;
  indicator: string;
  indicatorPeriod: string;
  low: string;
  high: string;
  not?: boolean;
  role: "ENTRY_FILTER" | "BENCHMARK_FILTER" | "EXIT_CONDITION";
  isBenchmark?: boolean;
  benchmarkSymbol?: string;
  rawExpression?: string;
  label?: string;
}

export interface ParsedRiskRule {
  type: "ATR_TRAILING_STOP" | "FIXED_STOP" | "TRAILING_STOP" | "RATCHET_STOP";
  atrLength?: number;
  atrMethod?: "SMA_TR" | "RMA_TR" | "EMA_TR"; // SMA of True Range (SMA_TR) vs Wilder's RMA
  multiplier?: number;
  hwmSource?: "CLOSE" | "HIGH"; // Highest Close vs High
  ratchet?: boolean;
  description: string;
}

export interface ParsedExitCondition {
  id: string;
  conditionText: string;
  action: "strategy.close" | "strategy.exit";
  reason?: string;
  rule?: ParsedCondition;
}

export interface ParsedRanking {
  field: string;
  period?: number;
  direction: "asc" | "desc";
  description: string;
}

export interface ParsedIndicator {
  name: string;
  period?: number;
  source?: string;
  type: string;
  usedInEntry: boolean;
  usedInExit: boolean;
}

export interface ResolvedCondition {
  rawExpression: string;
  serialized: string;
  role: ExpressionRole;
  filter?: ModalBuilderFilter;
  description?: string;
  sourceLine?: number;
}

export interface DebugTraceEntry {
  expression: string;
  resolved: string;
  role: ExpressionRole;
  builderField: string;
}

export interface ParsedStrategy {
  name: string;
  version?: number;
  direction: "LONG" | "SHORT" | "LONG_SHORT";
  executionLogic: "ALL" | "ANY";
  entryConditions: ParsedCondition[];
  benchmarkConditions: ParsedCondition[];
  exitConditions: ParsedExitCondition[];
  riskManagement: ParsedRiskRule[];
  ranking?: ParsedRanking;
  indicators: ParsedIndicator[];
  validityGuards: string[];
  positionGuards: string[];
  orderControlGuards: string[];
  warnings: string[];
  unsupportedFeatures: string[];
  debugTrace?: DebugTraceEntry[];
}

export interface PineParseResult {
  success: boolean;
  strategyName: string;
  description: string;
  positionSide: "LONG" | "SHORT";
  logic: "ALL" | "ANY";
  filters: ModalBuilderFilter[];
  pineVersion: string;
  versionWarning?: string | null;
  detectedFiltersCount: number;
  unsupportedCount: number;
  warnings: string[];
  errors: string[];
  isComplexLogic?: boolean;
  parsedStrategy?: ParsedStrategy;
  riskRules?: ParsedRiskRule[];
  exitConditions?: ParsedExitCondition[];
  benchmarkFilter?: ParsedCondition | null;
  rankingRule?: ParsedRanking | null;
  debugTrace?: DebugTraceEntry[];
}

export const DEFAULT_PINE_TEMPLATE = `//@version=6
strategy("52-Week High Breakout", overlay=true, pyramiding=0)

// ============================================================================
// 52-WEEK HIGH BREAKOUT STRATEGY
// ============================================================================

// 1. Market Gate (NIFTY 500 Trend)
benchmarkSymbol = "NSE:NIFTY500"
niftyClose = request.security(benchmarkSymbol, timeframe.period, close)
niftySma50 = request.security(benchmarkSymbol, timeframe.period, ta.sma(close, 50))
marketOk = niftyClose > niftySma50

// 2. 52-Week High Breakout (Prior 252-session High)
high252 = ta.highest(high, 252)
high252Prior = high252[1]
breakoutCondition = not na(high252Prior) and close >= high252Prior

// 3. Volume Gate (20-session SMA)
volumeLength = 20
volumeSma20 = ta.sma(volume, volumeLength)
volumeCondition = volume > volumeSma20

// 4. Candidate Ranking (Momentum 60)
momentum60 = close / close[60] - 1

// Safety & Data Validity
var bool soldThisBar = false
if ta.change(time) != 0
    soldThisBar := false

// Entry Trigger: All entry conditions must be true
longCondition = marketOk and breakoutCondition and volumeCondition and not na(close) and close > 0 and not soldThisBar

if longCondition and strategy.position_size == 0
    strategy.entry("Long", strategy.long)

// 5. Risk Management: ATR Trailing Stop (SMA of True Range, 3x Multiplier)
atrLength = 14
trueRange = math.max(high - low, math.max(math.abs(high - close[1]), math.abs(low - close[1])))
atr14 = ta.sma(trueRange, atrLength)

var float highWaterMark = na
var float trailingStop = na

if strategy.position_size > 0
    if bar_index > strategy.opentrades.entry_bar_index(0)
        if close > highWaterMark or na(highWaterMark)
            highWaterMark := close
            trailingStop := math.max(nz(trailingStop, close - 3 * atr14), close - 3 * atr14)
        if not na(trailingStop) and close < trailingStop
            strategy.close("Long", comment="atr_trail")
            soldThisBar := true
`;

// Token definition
type TokenType =
  | "NUMBER"
  | "STRING"
  | "IDENTIFIER"
  | "OPERATOR"
  | "KEYWORD"
  | "PUNCTUATION"
  | "EOF";

type Token = {
  type: TokenType;
  value: string;
  line: number;
  column: number;
};

export type PineExpr =
  | { type: "literal"; value: number | string | boolean; line: number }
  | { type: "identifier"; name: string; line: number }
  | { type: "offset"; base: PineExpr; offset: number; line: number }
  | { type: "call"; callee: string; args: Array<{ name?: string; value: PineExpr }>; line: number }
  | { type: "binary"; operator: string; left: PineExpr; right: PineExpr; line: number }
  | { type: "unary"; operator: string; argument: PineExpr; line: number }
  | { type: "group"; expression: PineExpr; line: number }
  | { type: "unsupported"; text: string; line: number };

export type PineStmt =
  | { type: "strategy_decl"; name: string; options: Record<string, PineExpr>; line: number }
  | { type: "assign"; name: string; op: "=" | ":="; value: PineExpr; varType?: string; isVar?: boolean; line: number }
  | { type: "entry"; id: string; direction: "LONG" | "SHORT"; when?: PineExpr; line: number }
  | { type: "close"; id: string; when?: PineExpr; line: number }
  | { type: "exit"; id: string; fromEntry?: string; stop?: PineExpr; limit?: PineExpr; trailPoints?: PineExpr; trailOffset?: PineExpr; when?: PineExpr; line: number }
  | { type: "if"; condition: PineExpr; thenBody: PineStmt[]; elseBody?: PineStmt[]; line: number }
  | { type: "expr_stmt"; expr: PineExpr; line: number };

const PINE_KEYWORDS = new Set([
  "and",
  "or",
  "not",
  "if",
  "else",
  "true",
  "false",
  "var",
  "varip",
  "int",
  "float",
  "bool",
  "string",
]);

// Tokenizer implementation
class PineLexer {
  private input: string;
  private pos: number = 0;
  private line: number = 1;
  private col: number = 1;

  constructor(input: string) {
    this.input = input;
  }

  tokenize(): { tokens: Token[]; version: number | null; comments: string[]; errors: string[] } {
    const tokens: Token[] = [];
    const comments: string[] = [];
    const errors: string[] = [];
    let version: number | null = null;

    while (this.pos < this.input.length) {
      const ch = this.input[this.pos];

      // Newlines & line tracking
      if (ch === "\n") {
        this.pos++;
        this.line++;
        this.col = 1;
        continue;
      }
      if (ch === "\r") {
        this.pos++;
        continue;
      }
      if (/\s/.test(ch)) {
        this.pos++;
        this.col++;
        continue;
      }

      // Single line comments & //@version directive
      if (ch === "/" && this.input[this.pos + 1] === "/") {
        let comment = "";
        while (this.pos < this.input.length && this.input[this.pos] !== "\n") {
          comment += this.input[this.pos];
          this.pos++;
          this.col++;
        }
        comments.push(comment.trim());

        const vMatch = comment.match(/\/\/\s*@version\s*=\s*(\d+)/i);
        if (vMatch && vMatch[1]) {
          version = parseInt(vMatch[1], 10);
        }
        continue;
      }

      // Multi-line comments
      if (ch === "/" && this.input[this.pos + 1] === "*") {
        let comment = "";
        this.pos += 2;
        this.col += 2;
        while (this.pos < this.input.length && !(this.input[this.pos] === "*" && this.input[this.pos + 1] === "/")) {
          if (this.input[this.pos] === "\n") {
            this.line++;
            this.col = 1;
          } else {
            this.col++;
          }
          comment += this.input[this.pos];
          this.pos++;
        }
        this.pos += 2;
        this.col += 2;
        comments.push(comment.trim());
        continue;
      }

      // Strings (single or double quote)
      if (ch === '"' || ch === "'") {
        const quote = ch;
        const startLine = this.line;
        const startCol = this.col;
        let str = "";
        this.pos++;
        this.col++;
        while (this.pos < this.input.length && this.input[this.pos] !== quote) {
          if (this.input[this.pos] === "\\") {
            this.pos++;
            this.col++;
            if (this.pos < this.input.length) {
              str += this.input[this.pos];
              this.pos++;
              this.col++;
            }
            continue;
          }
          if (this.input[this.pos] === "\n") {
            this.line++;
            this.col = 1;
          } else {
            this.col++;
          }
          str += this.input[this.pos];
          this.pos++;
        }
        if (this.pos < this.input.length && this.input[this.pos] === quote) {
          this.pos++;
          this.col++;
        } else {
          errors.push(`Line ${startLine}: Unterminated string literal`);
        }
        tokens.push({ type: "STRING", value: str, line: startLine, column: startCol });
        continue;
      }

      // Numeric literals
      if (/\d/.test(ch) || (ch === "." && /\d/.test(this.input[this.pos + 1] || ""))) {
        const startCol = this.col;
        let num = "";
        let hasDot = false;
        while (this.pos < this.input.length && (/\d/.test(this.input[this.pos]) || (this.input[this.pos] === "." && !hasDot))) {
          if (this.input[this.pos] === ".") hasDot = true;
          num += this.input[this.pos];
          this.pos++;
          this.col++;
        }
        tokens.push({ type: "NUMBER", value: num, line: this.line, column: startCol });
        continue;
      }

      // Identifiers / keywords (supports dotted identifiers like ta.sma, math.max, strategy.opentrades.entry_bar_index)
      if (/[a-zA-Z_]/.test(ch)) {
        const startCol = this.col;
        let ident = "";
        while (this.pos < this.input.length && /[a-zA-Z0-9_.]/.test(this.input[this.pos])) {
          if (this.input[this.pos] === "." && !/[a-zA-Z0-9_]/.test(this.input[this.pos + 1] || "")) {
            break;
          }
          ident += this.input[this.pos];
          this.pos++;
          this.col++;
        }

        const lower = ident.toLowerCase();
        if (PINE_KEYWORDS.has(lower)) {
          tokens.push({ type: "KEYWORD", value: lower, line: this.line, column: startCol });
        } else {
          tokens.push({ type: "IDENTIFIER", value: ident, line: this.line, column: startCol });
        }
        continue;
      }

      // Multi-character operators
      const twoChar = this.input.slice(this.pos, this.pos + 2);
      if (twoChar === ":=" || twoChar === "==" || twoChar === "!=" || twoChar === ">=" || twoChar === "<=" || twoChar === "&&" || twoChar === "||") {
        tokens.push({ type: "OPERATOR", value: twoChar, line: this.line, column: this.col });
        this.pos += 2;
        this.col += 2;
        continue;
      }

      // Single-character operators & punctuation
      if ("> < = + - * / % !".includes(ch)) {
        tokens.push({ type: "OPERATOR", value: ch, line: this.line, column: this.col });
        this.pos++;
        this.col++;
        continue;
      }

      if ("( ) [ ] { } , : ; ?".includes(ch)) {
        tokens.push({ type: "PUNCTUATION", value: ch, line: this.line, column: this.col });
        this.pos++;
        this.col++;
        continue;
      }

      errors.push(`Line ${this.line}: Unexpected character '${ch}'`);
      this.pos++;
      this.col++;
    }

    tokens.push({ type: "EOF", value: "", line: this.line, column: this.col });
    return { tokens, version, comments, errors };
  }
}

// Expression Parser
export class PineParser {
  private tokens: Token[];
  private current: number = 0;
  public errors: string[] = [];

  constructor(tokens: Token[]) {
    this.tokens = tokens;
  }

  private peek(): Token {
    return this.tokens[this.current] || { type: "EOF", value: "", line: 0, column: 0 };
  }

  private isAtEnd(): boolean {
    return this.peek().type === "EOF";
  }

  private advance(): Token {
    if (!this.isAtEnd()) this.current++;
    return this.tokens[this.current - 1];
  }

  private match(type: TokenType, ...values: string[]): boolean {
    const t = this.peek();
    if (t.type === type) {
      if (values.length === 0 || values.includes(t.value)) {
        this.advance();
        return true;
      }
    }
    return false;
  }

  private expect(type: TokenType, value?: string, errMsg?: string): Token {
    const t = this.peek();
    if (t.type === type && (!value || t.value === value)) {
      return this.advance();
    }
    const msg = errMsg || `Line ${t.line}: Expected '${value || type}' but found '${t.value || t.type}'`;
    this.errors.push(msg);
    return this.advance();
  }

  public parseExpression(): PineExpr {
    return this.parseLogicalOr();
  }

  private parseLogicalOr(): PineExpr {
    let expr = this.parseLogicalAnd();
    while (this.match("KEYWORD", "or") || this.match("OPERATOR", "||")) {
      const line = this.tokens[this.current - 1].line;
      const right = this.parseLogicalAnd();
      expr = { type: "binary", operator: "or", left: expr, right, line };
    }
    return expr;
  }

  private parseLogicalAnd(): PineExpr {
    let expr = this.parseEquality();
    while (this.match("KEYWORD", "and") || this.match("OPERATOR", "&&")) {
      const line = this.tokens[this.current - 1].line;
      const right = this.parseEquality();
      expr = { type: "binary", operator: "and", left: expr, right, line };
    }
    return expr;
  }

  private parseEquality(): PineExpr {
    let expr = this.parseRelational();
    while (this.match("OPERATOR", "==", "!=")) {
      const op = this.tokens[this.current - 1].value;
      const line = this.tokens[this.current - 1].line;
      const right = this.parseRelational();
      expr = { type: "binary", operator: op, left: expr, right, line };
    }
    return expr;
  }

  private parseRelational(): PineExpr {
    let expr = this.parseAdditive();
    while (this.match("OPERATOR", ">", "<", ">=", "<=")) {
      const op = this.tokens[this.current - 1].value;
      const line = this.tokens[this.current - 1].line;
      const right = this.parseAdditive();
      expr = { type: "binary", operator: op, left: expr, right, line };
    }
    return expr;
  }

  private parseAdditive(): PineExpr {
    let expr = this.parseMultiplicative();
    while (this.match("OPERATOR", "+", "-")) {
      const op = this.tokens[this.current - 1].value;
      const line = this.tokens[this.current - 1].line;
      const right = this.parseMultiplicative();
      expr = { type: "binary", operator: op, left: expr, right, line };
    }
    return expr;
  }

  private parseMultiplicative(): PineExpr {
    let expr = this.parseUnary();
    while (this.match("OPERATOR", "*", "/", "%")) {
      const op = this.tokens[this.current - 1].value;
      const line = this.tokens[this.current - 1].line;
      const right = this.parseUnary();
      expr = { type: "binary", operator: op, left: expr, right, line };
    }
    return expr;
  }

  private parseUnary(): PineExpr {
    if (this.match("KEYWORD", "not") || this.match("OPERATOR", "!") || this.match("OPERATOR", "-")) {
      const op = this.tokens[this.current - 1].value;
      const line = this.tokens[this.current - 1].line;
      const argument = this.parseUnary();
      return { type: "unary", operator: op === "!" ? "not" : op, argument, line };
    }
    return this.parsePostfix();
  }

  private parsePostfix(): PineExpr {
    let expr = this.parsePrimary();

    while (true) {
      if (this.match("PUNCTUATION", "[")) {
        const line = this.tokens[this.current - 1].line;
        const offsetToken = this.expect("NUMBER", undefined, `Line ${line}: Expected offset number in [index]`);
        const offset = parseInt(offsetToken.value, 10) || 1;
        this.expect("PUNCTUATION", "]", `Line ${line}: Expected ']'`);
        expr = { type: "offset", base: expr, offset, line };
        continue;
      }
      break;
    }

    return expr;
  }

  private parsePrimary(): PineExpr {
    const t = this.peek();

    if (this.match("NUMBER")) {
      const val = parseFloat(t.value);
      return { type: "literal", value: val, line: t.line };
    }

    if (this.match("STRING")) {
      return { type: "literal", value: t.value, line: t.line };
    }

    if (this.match("KEYWORD", "true")) {
      return { type: "literal", value: true, line: t.line };
    }

    if (this.match("KEYWORD", "false")) {
      return { type: "literal", value: false, line: t.line };
    }

    if (this.match("PUNCTUATION", "(")) {
      const line = t.line;
      const expression = this.parseExpression();
      this.expect("PUNCTUATION", ")", `Line ${line}: Unclosed '(' in expression`);
      return { type: "group", expression, line };
    }

    if (this.match("IDENTIFIER")) {
      const name = t.value;
      const line = t.line;

      // Function call
      if (this.match("PUNCTUATION", "(")) {
        const args: Array<{ name?: string; value: PineExpr }> = [];
        if (!this.match("PUNCTUATION", ")")) {
          do {
            let argName: string | undefined;
            if (this.peek().type === "IDENTIFIER" && this.tokens[this.current + 1]?.value === "=") {
              argName = this.advance().value;
              this.advance(); // skip '='
            }
            const argVal = this.parseExpression();
            args.push({ name: argName, value: argVal });
          } while (this.match("PUNCTUATION", ","));
          this.expect("PUNCTUATION", ")", `Line ${line}: Unclosed '(' in '${name}()' call`);
        }
        return { type: "call", callee: name, args, line };
      }

      return { type: "identifier", name, line };
    }

    const errLine = t.line || 1;
    this.errors.push(`Line ${errLine}: Unexpected token '${t.value || t.type}'`);
    this.advance();
    return { type: "unsupported", text: t.value, line: errLine };
  }
}

/**
 * Statement parser that builds AST statements, recognizes strategy.entry vs strategy.close,
 * if blocks, variables, security calls, True Range, ATR, and Trailing Stops.
 */
class PineStatementParser {
  private tokens: Token[];
  private pos: number = 0;
  public errors: string[] = [];

  constructor(tokens: Token[]) {
    this.tokens = tokens;
  }

  private peek(): Token {
    return this.tokens[this.pos] || { type: "EOF", value: "", line: 0, column: 0 };
  }

  private isAtEnd(): boolean {
    return this.peek().type === "EOF";
  }

  public parseStatements(): PineStmt[] {
    const stmts: PineStmt[] = [];
    while (!this.isAtEnd()) {
      const stmt = this.parseNextStatement();
      if (stmt) stmts.push(stmt);
    }
    return stmts;
  }

  private parseNextStatement(): PineStmt | null {
    const t = this.peek();

    // 1. strategy("Title", ...) / indicator("Title", ...) declaration
    if (t.type === "IDENTIFIER" && (t.value === "strategy" || t.value === "indicator") && this.tokens[this.pos + 1]?.value === "(") {
      const exprTokens = this.collectCallTokens();
      const parser = new PineParser(exprTokens);
      const call = parser.parseExpression();
      this.errors.push(...parser.errors);
      if (call.type === "call") {
        let name = "52-Week High Breakout";
        const options: Record<string, PineExpr> = {};
        if (call.args.length > 0 && call.args[0].value.type === "literal" && typeof call.args[0].value.value === "string") {
          name = call.args[0].value.value;
        }
        call.args.forEach((a, i) => {
          if (a.name) {
            options[a.name] = a.value;
            if (a.name === "title" && a.value.type === "literal" && typeof a.value.value === "string") {
              name = a.value.value;
            }
          } else if (i === 0 && a.value.type === "literal" && typeof a.value.value === "string") {
            name = a.value.value;
          }
        });
        return { type: "strategy_decl", name, options, line: t.line };
      }
    }

    // 2. strategy.entry(...)
    if (t.type === "IDENTIFIER" && t.value === "strategy.entry") {
      const exprTokens = this.collectCallTokens();
      const parser = new PineParser(exprTokens);
      const call = parser.parseExpression();
      this.errors.push(...parser.errors);
      let id = "Long";
      let direction: "LONG" | "SHORT" = "LONG";
      let whenExpr: PineExpr | undefined;

      if (call.type === "call") {
        if (call.args[0]?.value.type === "literal" && typeof call.args[0].value.value === "string") {
          id = call.args[0].value.value;
        }
        const dirArg = call.args[1]?.value || call.args.find((a) => a.name === "direction")?.value;
        if (dirArg) {
          const dirStr = serializeExpr(dirArg).toLowerCase();
          if (dirStr.includes("short") || dirStr.includes("false")) {
            direction = "SHORT";
          } else {
            direction = "LONG";
          }
        }
        const whenArg = call.args.find((a) => a.name === "when")?.value;
        if (whenArg) whenExpr = whenArg;
      }
      return { type: "entry", id, direction, when: whenExpr, line: t.line };
    }

    // 3. strategy.close(...)
    if (t.type === "IDENTIFIER" && t.value === "strategy.close") {
      const exprTokens = this.collectCallTokens();
      const parser = new PineParser(exprTokens);
      const call = parser.parseExpression();
      this.errors.push(...parser.errors);
      let id = "Long";
      let whenExpr: PineExpr | undefined;
      if (call.type === "call") {
        if (call.args[0]?.value.type === "literal" && typeof call.args[0].value.value === "string") {
          id = call.args[0].value.value;
        }
        const whenArg = call.args.find((a) => a.name === "when")?.value;
        if (whenArg) whenExpr = whenArg;
      }
      return { type: "close", id, when: whenExpr, line: t.line };
    }

    // 4. strategy.exit(...)
    if (t.type === "IDENTIFIER" && t.value === "strategy.exit") {
      const exprTokens = this.collectCallTokens();
      const parser = new PineParser(exprTokens);
      const call = parser.parseExpression();
      this.errors.push(...parser.errors);
      let id = "Exit";
      let fromEntry: string | undefined;
      let stop: PineExpr | undefined;
      let limit: PineExpr | undefined;
      let whenExpr: PineExpr | undefined;

      if (call.type === "call") {
        if (call.args[0]?.value.type === "literal" && typeof call.args[0].value.value === "string") {
          id = call.args[0].value.value;
        }
        if (call.args[1]?.value.type === "literal" && typeof call.args[1].value.value === "string") {
          fromEntry = call.args[1].value.value;
        }
        stop = call.args.find((a) => a.name === "stop")?.value;
        limit = call.args.find((a) => a.name === "limit")?.value;
        whenExpr = call.args.find((a) => a.name === "when")?.value;
      }
      return { type: "exit", id, fromEntry, stop, limit, when: whenExpr, line: t.line };
    }

    // 5. if statement
    if (t.type === "KEYWORD" && t.value === "if") {
      const ifLine = t.line;
      this.pos++; // skip 'if'
      // Condition expression tokens
      const condTokens: Token[] = [];
      while (!this.isAtEnd()) {
        const curr = this.peek();
        if (curr.value === "strategy.entry" || curr.value === "strategy.close" || curr.value === "strategy.exit") {
          break;
        }
        if (curr.type === "KEYWORD" && curr.value === "if") {
          break;
        }
        if (curr.type === "IDENTIFIER" && (this.tokens[this.pos + 1]?.value === "=" || this.tokens[this.pos + 1]?.value === ":=")) {
          break;
        }
        condTokens.push(curr);
        this.pos++;
      }
      condTokens.push({ type: "EOF", value: "", line: ifLine, column: 0 });
      const parser = new PineParser(condTokens);
      const condition = parser.parseExpression();
      this.errors.push(...parser.errors);

      const thenBody: PineStmt[] = [];
      while (!this.isAtEnd()) {
        const next = this.peek();
        if (next.type === "KEYWORD" && next.value === "if") {
          const nested = this.parseNextStatement();
          if (nested) thenBody.push(nested);
          continue;
        }
        if (
          next.value === "strategy.entry" ||
          next.value === "strategy.close" ||
          next.value === "strategy.exit" ||
          (next.type === "IDENTIFIER" && (this.tokens[this.pos + 1]?.value === "=" || this.tokens[this.pos + 1]?.value === ":="))
        ) {
          const bodyStmt = this.parseNextStatement();
          if (bodyStmt) thenBody.push(bodyStmt);
          continue;
        }
        break;
      }

      return { type: "if", condition, thenBody, line: ifLine };
    }

    // 6. Variable declaration / assignment
    let varName = "";
    let op: "=" | ":=" = "=";
    let isVar = false;
    let varType: string | undefined;

    if (t.type === "IDENTIFIER" && (this.tokens[this.pos + 1]?.value === "=" || this.tokens[this.pos + 1]?.value === ":=")) {
      varName = t.value;
      op = this.tokens[this.pos + 1].value as "=" | ":=";
      this.pos += 2;
    } else if (
      (t.value === "var" || t.value === "varip") &&
      this.tokens[this.pos + 1]?.type === "IDENTIFIER" &&
      (this.tokens[this.pos + 2]?.value === "=" || this.tokens[this.pos + 2]?.value === ":=")
    ) {
      isVar = true;
      varName = this.tokens[this.pos + 1].value;
      op = this.tokens[this.pos + 2].value as "=" | ":=";
      this.pos += 3;
    } else if (
      (t.value === "var" || t.value === "varip") &&
      (this.tokens[this.pos + 1]?.value === "float" || this.tokens[this.pos + 1]?.value === "int" || this.tokens[this.pos + 1]?.value === "bool" || this.tokens[this.pos + 1]?.value === "string") &&
      this.tokens[this.pos + 2]?.type === "IDENTIFIER" &&
      (this.tokens[this.pos + 3]?.value === "=" || this.tokens[this.pos + 3]?.value === ":=")
    ) {
      isVar = true;
      varType = this.tokens[this.pos + 1].value;
      varName = this.tokens[this.pos + 2].value;
      op = this.tokens[this.pos + 3].value as "=" | ":=";
      this.pos += 4;
    }

    if (varName) {
      const exprTokens = this.collectStatementTokens();
      const parser = new PineParser(exprTokens);
      const value = parser.parseExpression();
      this.errors.push(...parser.errors);
      return { type: "assign", name: varName, op, value, isVar, varType, line: t.line };
    }

    this.pos++;
    return null;
  }

  private collectCallTokens(): Token[] {
    const startLine = this.peek().line;
    const tokens: Token[] = [];
    let parenDepth = 0;
    while (!this.isAtEnd()) {
      const curr = this.peek();
      tokens.push(curr);
      this.pos++;
      if (curr.value === "(") parenDepth++;
      else if (curr.value === ")") {
        parenDepth--;
        if (parenDepth === 0) break;
      }
    }
    tokens.push({ type: "EOF", value: "", line: startLine, column: 0 });
    return tokens;
  }

  private collectStatementTokens(): Token[] {
    const startLine = this.peek().line;
    const tokens: Token[] = [];
    let parenDepth = 0;
    let bracketDepth = 0;

    while (!this.isAtEnd()) {
      const curr = this.peek();
      if (curr.value === "(") parenDepth++;
      else if (curr.value === ")") parenDepth--;
      else if (curr.value === "[") bracketDepth++;
      else if (curr.value === "]") bracketDepth--;

      if (parenDepth === 0 && bracketDepth === 0) {
        if (
          curr.value === "if" ||
          curr.value === "strategy" ||
          curr.value === "strategy.entry" ||
          curr.value === "strategy.close" ||
          curr.value === "strategy.exit" ||
          (curr.type === "IDENTIFIER" && (this.tokens[this.pos + 1]?.value === "=" || this.tokens[this.pos + 1]?.value === ":="))
        ) {
          break;
        }
      }
      tokens.push(curr);
      this.pos++;
    }
    tokens.push({ type: "EOF", value: "", line: startLine, column: 0 });
    return tokens;
  }
}

/**
 * Main parser entry point with Semantic Role Classification & Data-Flow Isolation.
 */
export function parsePineScript(code: string, options?: { debug?: boolean }): PineParseResult {
  const warnings: string[] = [];
  const errors: string[] = [];
  const debugTrace: DebugTraceEntry[] = [];

  const trimmed = code ? code.trim() : "";
  if (!trimmed) {
    return {
      success: false,
      strategyName: "52-Week High Breakout",
      description: "",
      positionSide: "LONG",
      logic: "ALL",
      filters: [],
      pineVersion: "v6",
      detectedFiltersCount: 0,
      unsupportedCount: 0,
      warnings: [],
      errors: ["Please enter Pine Script code first."],
      debugTrace: [],
    };
  }

  // 1. Tokenize & Version detection
  const lexer = new PineLexer(code);
  const { tokens, version, comments, errors: lexErrors } = lexer.tokenize();
  errors.push(...lexErrors);

  let pineVersionStr = "v6";
  let versionWarning: string | null = null;
  if (version != null) {
    pineVersionStr = `v${version}`;
    if (version !== 5 && version !== 6) {
      versionWarning = `Unsupported Pine Script version (${pineVersionStr}). Please use Pine Script v5/v6.`;
      warnings.push(versionWarning);
    }
  }

  // 2. Parse Statements into AST
  const stmtParser = new PineStatementParser(tokens);
  const statements = stmtParser.parseStatements();
  errors.push(...stmtParser.errors);

  // 3. Collect Declarations, Assignments & Strategy Actions
  let strategyName = "52-Week High Breakout";
  let explicitLong = false;
  let explicitShort = false;

  const scope = new Map<string, PineExpr>();
  const entryGuards: PineExpr[] = [];
  const exitGuards: PineExpr[] = [];
  const exitActions: ParsedExitCondition[] = [];
  const riskRules: ParsedRiskRule[] = [];
  const validityGuardsCollected: string[] = [];
  const positionGuardsCollected: string[] = [];
  const orderControlGuardsCollected: string[] = [];

  // Traverse statements and assign roles
  function processStatement(stmt: PineStmt, currentGuard: PineExpr | null) {
    if (stmt.type === "strategy_decl") {
      strategyName = stmt.name;
      return;
    }

    if (stmt.type === "assign") {
      scope.set(stmt.name, stmt.value);
      return;
    }

    if (stmt.type === "entry") {
      if (stmt.direction === "SHORT") {
        explicitShort = true;
      } else {
        explicitLong = true;
      }

      let fullCondition = currentGuard;
      if (stmt.when) {
        fullCondition = fullCondition ? { type: "binary", operator: "and", left: fullCondition, right: stmt.when, line: stmt.line } : stmt.when;
      }
      if (fullCondition) {
        entryGuards.push(fullCondition);
      }
      return;
    }

    if (stmt.type === "close") {
      // Isolate actual exit trigger from nested position guards
      const exitTrigger = extractPureExitCondition(currentGuard, stmt.when, scope);
      if (exitTrigger) {
        exitGuards.push(exitTrigger);
        exitActions.push({
          id: `exit_${exitActions.length + 1}`,
          conditionText: formatExitConditionText(exitTrigger, scope),
          action: "strategy.close",
          reason: "atr_trail",
        });
      } else {
        exitActions.push({
          id: `exit_${exitActions.length + 1}`,
          conditionText: "Close < Trailing Stop",
          action: "strategy.close",
          reason: "atr_trail",
        });
      }
      return;
    }

    if (stmt.type === "exit") {
      const exitTrigger = extractPureExitCondition(currentGuard, stmt.when, scope);
      const text = stmt.stop ? `Stop: ${serializeExpr(stmt.stop)}` : exitTrigger ? formatExitConditionText(exitTrigger, scope) : "Position Exit";
      exitActions.push({
        id: `exit_${exitActions.length + 1}`,
        conditionText: text,
        action: "strategy.exit",
        reason: "risk_stop",
      });
      return;
    }

    if (stmt.type === "if") {
      const combined = currentGuard ? { type: "binary", operator: "and", left: currentGuard, right: stmt.condition, line: stmt.line } : stmt.condition;
      for (const child of stmt.thenBody) {
        processStatement(child, combined);
      }
      return;
    }
  }

  for (const stmt of statements) {
    processStatement(stmt, null);
  }

  // Determine Direction
  const positionSide: "LONG" | "SHORT" = explicitShort && !explicitLong ? "SHORT" : "LONG";

  // Clean description derivation
  const description = extractCleanDescription(comments, strategyName);

  // 4. Data-Flow Dependency Resolution for Entry Predicates
  let rootEntryExpr: PineExpr | null = null;

  if (entryGuards.length > 0) {
    if (entryGuards.length === 1) {
      rootEntryExpr = entryGuards[0];
    } else {
      let combined = entryGuards[0];
      for (let i = 1; i < entryGuards.length; i++) {
        combined = { type: "binary", operator: "and", left: combined, right: entryGuards[i], line: 0 };
      }
      rootEntryExpr = combined;
    }
  } else {
    const entryCandidateNames = [
      "longCondition",
      "long_condition",
      "longCond",
      "scanSignal",
      "scan_signal",
      "buyCondition",
      "buy_condition",
      "buySignal",
      "entryCondition",
      "entry_condition",
      "breakoutCondition",
      "breakout",
      "shortCondition",
      "short_condition",
      "shortCond",
      "sellCondition",
      "sell_condition",
      "sellSignal",
    ];

    for (const name of entryCandidateNames) {
      if (scope.has(name)) {
        rootEntryExpr = scope.get(name)!;
        break;
      }
    }
  }

  // 5. Analyze Risk Management (ATR, True Range, Trailing Stop, Ratchet)
  analyzeRiskManagement(scope, exitGuards, riskRules, debugTrace);

  // 6. Analyze Ranking expressions (e.g. momentum60 = close / close[60] - 1)
  let rankingRule: ParsedRanking | null = null;
  for (const [varName, expr] of scope.entries()) {
    const rank = analyzeRankingExpr(varName, expr);
    if (rank) {
      rankingRule = rank;
      debugTrace.push({
        expression: `${varName} = ${serializeExpr(expr)}`,
        resolved: rank.description,
        role: "RANKING",
        builderField: `Ranking: ${rank.description}`,
      });
    }
  }

  // 7. Collect Declared Indicators and Check Usage
  const indicators: ParsedIndicator[] = [];
  for (const [varName, expr] of scope.entries()) {
    const ind = extractIndicatorInfo(varName, expr, scope);
    if (ind) {
      const usedInEntry = rootEntryExpr ? referencesVariable(rootEntryExpr, varName, scope) : false;
      const usedInExit = exitGuards.some((g) => referencesVariable(g, varName, scope));
      ind.usedInEntry = usedInEntry;
      ind.usedInExit = usedInExit;
      indicators.push(ind);

      if (!usedInEntry && !usedInExit) {
        debugTrace.push({
          expression: `${varName} = ${serializeExpr(expr)}`,
          resolved: `${ind.name} ${ind.period || ""}`.trim(),
          role: "INDICATOR_DEFINITION",
          builderField: "(Unused indicator definition - not an entry filter)",
        });
      }
    }
  }

  // 8. If syntax/token errors occurred, return failure
  if (errors.length > 0) {
    return {
      success: false,
      strategyName,
      description,
      positionSide,
      logic: "ALL",
      filters: [],
      pineVersion: pineVersionStr,
      versionWarning,
      detectedFiltersCount: 0,
      unsupportedCount: 0,
      warnings,
      errors,
      debugTrace,
    };
  }

  // 9. Deconstruct Entry Conditions with Strict Semantic Role Classification
  const entryConditions: ParsedCondition[] = [];
  const benchmarkConditions: ParsedCondition[] = [];
  const filters: ModalBuilderFilter[] = [];
  const seenFilterKeys = new Set<string>();
  let logic: "ALL" | "ANY" = "ALL";
  let isComplex = false;
  let unsupportedCount = 0;

  if (rootEntryExpr) {
    const flat = flattenConditions(rootEntryExpr, scope);
    logic = flat.logic;
    isComplex = flat.isComplex;

    for (const term of flat.terms) {
      const resolved = classifyAndResolveCondition(term, scope, filters.length + 1, debugTrace);

      if (resolved.role === "VALIDITY_GUARD") {
        validityGuardsCollected.push(resolved.serialized);
        continue;
      }
      if (resolved.role === "POSITION_STATE") {
        positionGuardsCollected.push(resolved.serialized);
        continue;
      }
      if (resolved.role === "ORDER_CONTROL" || resolved.role === "ENTRY_BAR_PROTECTION") {
        orderControlGuardsCollected.push(resolved.serialized);
        continue;
      }
      if (resolved.role === "TRAILING_STOP_UPDATE" || resolved.role === "RISK_MANAGEMENT" || resolved.role === "EXIT_CONDITION" || resolved.role === "EXIT_GUARD") {
        continue;
      }

      if (resolved.filter && (resolved.role === "ENTRY_FILTER" || resolved.role === "BENCHMARK_FILTER")) {
        const filterKey = getFilterSemanticKey(resolved.filter);
        if (!seenFilterKeys.has(filterKey)) {
          seenFilterKeys.add(filterKey);
          filters.push(resolved.filter);
          if (resolved.role === "BENCHMARK_FILTER") {
            benchmarkConditions.push(resolved.filter as ParsedCondition);
          } else {
            entryConditions.push(resolved.filter as ParsedCondition);
          }
        }
      } else if (resolved.role === "UNSUPPORTED") {
        unsupportedCount++;
        warnings.push(`Line ${term.line}: '${resolved.serialized}' could not be converted into a supported filter.`);
      }
    }
  } else {
    warnings.push("No supported entry filters were detected. Please review the Pine Script or manually configure the Strategy Builder.");
  }

  if (isComplex) {
    warnings.push("Complex logical expression detected. The detected conditions have been imported, but the original nested logic requires manual review.");
  }

  if (filters.length === 0 && unsupportedCount > 0) {
    warnings.push("Unsupported condition detected. The condition could not be converted into a Strategy Builder filter. Please review manually.");
  }

  const parsedStrategy: ParsedStrategy = {
    name: strategyName,
    version: version || 6,
    direction: positionSide === "LONG" ? "LONG" : "SHORT",
    executionLogic: logic,
    entryConditions,
    benchmarkConditions,
    exitConditions: exitActions,
    riskManagement: riskRules,
    ranking: rankingRule || undefined,
    indicators,
    validityGuards: validityGuardsCollected,
    positionGuards: positionGuardsCollected,
    orderControlGuards: orderControlGuardsCollected,
    warnings,
    unsupportedFeatures: warnings.filter((w) => w.includes("Unsupported") || w.includes("Custom function")),
    debugTrace,
  };

  return {
    success: true,
    strategyName: strategyName || "52-Week High Breakout",
    description,
    positionSide,
    logic,
    filters,
    pineVersion: pineVersionStr,
    versionWarning,
    detectedFiltersCount: filters.length,
    unsupportedCount,
    warnings,
    errors: [],
    isComplexLogic: isComplex,
    parsedStrategy,
    riskRules,
    exitConditions: exitActions,
    benchmarkFilter: benchmarkConditions[0] || null,
    rankingRule,
    debugTrace,
  };
}

/**
 * Extracts a clean strategy description from comments without capturing separator headers (===, ---).
 */
function extractCleanDescription(comments: string[], fallbackName: string): string {
  for (const raw of comments) {
    const clean = raw.replace(/^\/\/\s*/, "").trim();
    if (!clean) continue;
    if (clean.startsWith("@version")) continue;
    if (clean.toLowerCase().startsWith("strategy(")) continue;
    // Discard separator lines: // ===, // ---, // ***, // ###
    if (/^[=\-_*#~]{3,}$/.test(clean)) continue;
    if (/^[=\-_*#~\s]+$/.test(clean)) continue;
    // Discard uppercase banner headers e.g. "52-WEEK HIGH BREAKOUT STRATEGY"
    if (clean === clean.toUpperCase() && clean.length < 40) continue;
    if (clean.toLowerCase().startsWith("strategy id:") || clean.toLowerCase().startsWith("author:")) continue;
    // Discard numbered section titles e.g. "1. Market Gate", "2. 52-Week High Breakout"
    if (/^\d+\.\s+/.test(clean)) continue;

    if (clean.length > 10 && /[a-zA-Z]/.test(clean)) {
      return clean;
    }
  }

  return `${fallbackName} based on price and volume filters.`;
}

/**
 * Classifies an AST expression node into its semantic role.
 */
function classifyAndResolveCondition(
  node: PineExpr,
  scope: Map<string, PineExpr>,
  idx: number,
  debugTrace: DebugTraceEntry[],
): ResolvedCondition {
  const serialized = serializeExpr(node);
  const lowerStr = serialized.toLowerCase().replace(/\s+/g, "");

  // 1. VALIDITY GUARDS: not na(...), !na(...), na(...), ta.change(time) != 0, close > 0, volume > 0
  if (
    lowerStr.includes("notna(") ||
    lowerStr.includes("!na(") ||
    lowerStr.startsWith("na(") ||
    lowerStr.includes("==na") ||
    lowerStr.includes("!=na") ||
    lowerStr.includes("nz(") ||
    lowerStr.includes("ta.change(time)")
  ) {
    debugTrace.push({
      expression: serialized,
      resolved: "Validity Guard (Data warmup check)",
      role: "VALIDITY_GUARD",
      builderField: "(Internal validity guard - ignored in Builder)",
    });
    return { rawExpression: serialized, serialized, role: "VALIDITY_GUARD" };
  }

  // Check for price / volume > 0 safety check
  if (node.type === "binary" && (node.operator === ">" || node.operator === ">=")) {
    const lStr = serializeExpr(node.left).toLowerCase();
    const rStr = serializeExpr(node.right).toLowerCase();
    if ((["close", "open", "high", "low", "volume"].includes(lStr) && rStr === "0") ||
        (["close", "open", "high", "low", "volume"].includes(rStr) && lStr === "0")) {
      debugTrace.push({
        expression: serialized,
        resolved: `${lStr} > 0 (Data validity check)`,
        role: "VALIDITY_GUARD",
        builderField: "(Internal validity guard - ignored in Builder)",
      });
      return { rawExpression: serialized, serialized, role: "VALIDITY_GUARD" };
    }
  }

  // 2. POSITION STATE: strategy.position_size, strategy.opentrades count
  if (lowerStr.includes("strategy.position_size") || lowerStr.includes("strategy.opentrades>0") || lowerStr.includes("strategy.opentrades==")) {
    debugTrace.push({
      expression: serialized,
      resolved: "Position State Context",
      role: "POSITION_STATE",
      builderField: "(Internal position state - ignored in Builder)",
    });
    return { rawExpression: serialized, serialized, role: "POSITION_STATE" };
  }

  // 3. ORDER CONTROL & ENTRY BAR PROTECTION: soldThisBar, bar_index > strategy.opentrades.entry_bar_index
  if (lowerStr.includes("soldthisbar") || lowerStr.includes("intrade") || lowerStr.includes("canenter") || lowerStr.includes("entryallowed") || lowerStr.includes("barstate.")) {
    debugTrace.push({
      expression: serialized,
      resolved: "Order Control (Re-entry / bar protection)",
      role: "ORDER_CONTROL",
      builderField: "(Internal order control - ignored in Builder)",
    });
    return { rawExpression: serialized, serialized, role: "ORDER_CONTROL" };
  }

  if (lowerStr.includes("entry_bar_index") || lowerStr.includes("bar_index>")) {
    debugTrace.push({
      expression: serialized,
      resolved: "Entry-Bar Protection",
      role: "ENTRY_BAR_PROTECTION",
      builderField: "(Internal bar protection - ignored in Builder)",
    });
    return { rawExpression: serialized, serialized, role: "ENTRY_BAR_PROTECTION" };
  }

  // 4. TRAILING STOP UPDATE: close > highWaterMark
  if (lowerStr.includes("highwatermark") || lowerStr.includes("hwm") || lowerStr.includes("highestclose")) {
    debugTrace.push({
      expression: serialized,
      resolved: "Trailing Stop Update Condition",
      role: "TRAILING_STOP_UPDATE",
      builderField: "(Internal risk update - ignored in Builder)",
    });
    return { rawExpression: serialized, serialized, role: "TRAILING_STOP_UPDATE" };
  }

  // 5. EXIT CONDITIONS: close < trailingStop
  if (lowerStr.includes("trailingstop") || lowerStr.includes("trailstop") || lowerStr.includes("stopprice")) {
    debugTrace.push({
      expression: serialized,
      resolved: "Exit Trigger Condition (Close < Trailing Stop)",
      role: "EXIT_CONDITION",
      builderField: "Exit Condition: Close < Trailing Stop",
    });
    return { rawExpression: serialized, serialized, role: "EXIT_CONDITION" };
  }

  // 6. BENCHMARK & ENTRY FILTERS
  const filter = normalizeTermToFilter(node, scope, idx, debugTrace);
  if (filter) {
    const role: ExpressionRole = filter.role === "BENCHMARK_FILTER" ? "BENCHMARK_FILTER" : "ENTRY_FILTER";
    return { rawExpression: serialized, serialized, role, filter };
  }

  return { rawExpression: serialized, serialized, role: "UNSUPPORTED" };
}

/**
 * Isolates the pure exit condition without flattening nested position-management if guards.
 */
function extractPureExitCondition(
  guard: PineExpr | null,
  when: PineExpr | undefined,
  scope: Map<string, PineExpr>,
): PineExpr | null {
  const candidates: PineExpr[] = [];
  if (when) candidates.push(when);
  if (guard) candidates.push(guard);

  for (const c of candidates) {
    const flat = flattenConditions(c, scope);
    for (const term of flat.terms) {
      const s = serializeExpr(term).toLowerCase();
      if ((s.includes("trail") || s.includes("stop")) && (s.includes("<") || s.includes("<="))) {
        return term;
      }
    }
  }

  for (const c of candidates) {
    const flat = flattenConditions(c, scope);
    for (const term of flat.terms) {
      const s = serializeExpr(term).toLowerCase();
      if (!s.includes("position_size") && !s.includes("bar_index") && !s.includes("highwatermark") && !s.includes("na(")) {
        return term;
      }
    }
  }

  return null;
}

function formatExitConditionText(expr: PineExpr, _scope: Map<string, PineExpr>): string {
  const str = serializeExpr(expr);
  const lower = str.toLowerCase().replace(/\s+/g, "");
  if (lower.includes("close<trailingstop") || lower.includes("close<=trailingstop") || lower.includes("close<trail")) {
    return "Close < Trailing Stop";
  }
  if (lower.includes("close<") && lower.includes("stop")) {
    return "Close < Trailing Stop";
  }
  return str;
}

/**
 * Risk Management analyzer for True Range, ATR lengths, multipliers, HWM, and ratcheting stops.
 */
function analyzeRiskManagement(
  scope: Map<string, PineExpr>,
  exitGuards: PineExpr[],
  riskRules: ParsedRiskRule[],
  debugTrace: DebugTraceEntry[],
) {
  let atrLength: number | undefined;
  let atrMethod: "SMA_TR" | "RMA_TR" | "EMA_TR" | undefined;
  let multiplier: number | undefined;
  let hwmSource: "CLOSE" | "HIGH" = "CLOSE";
  let hasRatchet = false;
  let hasTrailingStop = false;

  for (const [varName, expr] of scope.entries()) {
    const varLower = varName.toLowerCase();

    // 1. True Range detection
    if (varLower.includes("truerange") || varLower === "tr") {
      debugTrace.push({
        expression: `${varName} = ${serializeExpr(expr)}`,
        resolved: "True Range = max(high-low, abs(high-prevClose), abs(low-prevClose))",
        role: "RISK_MANAGEMENT",
        builderField: "Risk Management: True Range Calculation",
      });
    }

    // 2. ATR detection: ta.sma(trueRange, 14) vs ta.atr(14)
    if (varLower.includes("atr") || (expr.type === "call" && (expr.callee.includes("atr") || expr.callee.includes("sma") || expr.callee.includes("rma")))) {
      if (expr.type === "call") {
        const callee = expr.callee.toLowerCase();
        if (callee === "ta.sma" || callee === "sma") {
          const arg0 = expr.args[0]?.value ? serializeExpr(expr.args[0].value).toLowerCase() : "";
          if (arg0.includes("tr") || arg0.includes("truerange")) {
            atrMethod = "SMA_TR";
            atrLength = expr.args[1] ? extractNumber(expr.args[1].value, scope) || 14 : 14;
          }
        } else if (callee === "ta.atr" || callee === "atr") {
          atrMethod = "RMA_TR";
          atrLength = expr.args[0] ? extractNumber(expr.args[0].value, scope) || 14 : 14;
        } else if (callee === "ta.rma" || callee === "rma") {
          atrMethod = "RMA_TR";
          atrLength = expr.args[1] ? extractNumber(expr.args[1].value, scope) || 14 : 14;
        }
      }
    }

    // 3. Multiplier & Trailing stop formula: close - 3 * atr14
    if (varLower.includes("trail") || varLower.includes("stop")) {
      hasTrailingStop = true;
      const mult = extractMultiplier(expr, scope);
      if (mult) multiplier = mult;
    }

    // 4. High Water Mark: math.max(highWaterMark, close) or highWaterMark := close
    if (varLower.includes("hwm") || varLower.includes("highwatermark")) {
      const exprStr = serializeExpr(expr).toLowerCase();
      if (exprStr.includes("high") && !exprStr.includes("close")) {
        hwmSource = "HIGH";
      } else {
        hwmSource = "CLOSE";
      }
    }

    // 5. Ratchet detection: math.max(trailingStop, ...) or math.max(nz(trailingStop), ...)
    if (expr.type === "call" && (expr.callee === "math.max" || expr.callee === "max")) {
      const argStr = expr.args.map((a) => serializeExpr(a.value).toLowerCase()).join(" ");
      if (argStr.includes("trail") || argStr.includes("stop")) {
        hasRatchet = true;
      }
    }
  }

  // Check exit guards for ratcheting trailing stop
  for (const guard of exitGuards) {
    const gStr = serializeExpr(guard).toLowerCase();
    if (gStr.includes("trail") || gStr.includes("stop")) {
      hasTrailingStop = true;
    }
  }

  if (hasTrailingStop || atrLength != null) {
    const finalLength = atrLength || 14;
    const finalMethod = atrMethod || "SMA_TR";
    const finalMult = multiplier || 3;
    const methodLabel = finalMethod === "SMA_TR" ? "SMA of True Range" : "Wilder RMA";

    riskRules.push({
      type: "ATR_TRAILING_STOP",
      atrLength: finalLength,
      atrMethod: finalMethod,
      multiplier: finalMult,
      hwmSource,
      ratchet: hasRatchet || true,
      description: `Trailing Stop: Highest ${hwmSource === "CLOSE" ? "Close" : "High"} - ${finalMult} × ATR${finalLength} (${methodLabel}, Ratcheting)`,
    });

    debugTrace.push({
      expression: `ATR Trailing Stop (${finalLength}, ${finalMethod}, ${finalMult}x)`,
      resolved: `Highest ${hwmSource} - ${finalMult} * ATR${finalLength}`,
      role: "RISK_MANAGEMENT",
      builderField: `Risk Management: Trailing Stop: Highest Close - ${finalMult} × ATR${finalLength}`,
    });
  }
}

/**
 * Extracts candidate ranking expression: momentum60 = close / close[60] - 1 or ta.roc(close, 60)
 */
function analyzeRankingExpr(varName: string, expr: PineExpr): ParsedRanking | null {
  const nameLower = varName.toLowerCase();
  const isCandidateName = nameLower.includes("momentum") || nameLower.includes("roc") || nameLower.includes("rank");

  // Case 1: close / close[60] - 1
  if (expr.type === "binary" && (expr.operator === "-" || expr.operator === "/")) {
    const str = serializeExpr(expr);
    const offsetMatch = str.match(/close\s*\[\s*(\d+)\s*\]/i);
    if (offsetMatch && offsetMatch[1]) {
      const period = parseInt(offsetMatch[1], 10);
      return {
        field: "MOMENTUM",
        period,
        direction: "desc",
        description: `Momentum ${period} descending`,
      };
    }
  }

  // Case 2: ta.roc(close, 60)
  if (expr.type === "call" && (expr.callee === "ta.roc" || expr.callee === "roc")) {
    const period = expr.args[1] ? extractNumber(expr.args[1].value, new Map()) || 60 : 60;
    return {
      field: "ROC",
      period,
      direction: "desc",
      description: `Momentum ${period} (ROC) descending`,
    };
  }

  if (isCandidateName) {
    return {
      field: "MOMENTUM",
      period: 60,
      direction: "desc",
      description: `Momentum 60 descending`,
    };
  }

  return null;
}

/**
 * Extract indicator definition details without assuming it is an entry filter.
 */
function extractIndicatorInfo(varName: string, expr: PineExpr, scope: Map<string, PineExpr>): ParsedIndicator | null {
  let node: PineExpr = expr;
  if (node.type === "offset") node = node.base;
  if (node.type === "group") node = node.expression;
  if (node.type !== "call") return null;
  const callee = node.callee.toLowerCase();

  if (callee === "ta.sma" || callee === "sma") {
    const period = node.args[1] ? extractNumber(node.args[1].value, scope) || 50 : 50;
    return { name: "SMA", period, type: "trend", usedInEntry: false, usedInExit: false };
  }
  if (callee === "ta.ema" || callee === "ema") {
    const period = node.args[1] ? extractNumber(node.args[1].value, scope) || 20 : 20;
    return { name: "EMA", period, type: "trend", usedInEntry: false, usedInExit: false };
  }
  if (callee === "ta.rsi" || callee === "rsi") {
    const period = node.args.length >= 2 ? extractNumber(node.args[1].value, scope) || 14 : 14;
    return { name: "RSI", period, type: "momentum", usedInEntry: false, usedInExit: false };
  }
  if (callee === "ta.highest" || callee === "highest") {
    const period = node.args.length >= 2 ? extractNumber(node.args[1].value, scope) || 252 : 252;
    return { name: "HIGH", period, type: "price_extreme", usedInEntry: false, usedInExit: false };
  }
  if (callee === "ta.lowest" || callee === "lowest") {
    const period = node.args.length >= 2 ? extractNumber(node.args[1].value, scope) || 252 : 252;
    return { name: "LOW", period, type: "price_extreme", usedInEntry: false, usedInExit: false };
  }
  if (callee === "ta.atr" || callee === "atr") {
    const period = node.args[0] ? extractNumber(node.args[0].value, scope) || 14 : 14;
    return { name: "ATR", period, type: "volatility", usedInEntry: false, usedInExit: false };
  }
  return null;
}

function referencesVariable(expr: PineExpr, target: string, scope: Map<string, PineExpr>, visited: Set<string> = new Set()): boolean {
  if (expr.type === "identifier") {
    if (expr.name === target) return true;
    if (visited.has(expr.name)) return false;
    visited.add(expr.name);
    if (scope.has(expr.name)) {
      return referencesVariable(scope.get(expr.name)!, target, scope, visited);
    }
    return false;
  }
  if (expr.type === "binary") {
    return referencesVariable(expr.left, target, scope, visited) || referencesVariable(expr.right, target, scope, visited);
  }
  if (expr.type === "unary") {
    return referencesVariable(expr.argument, target, scope, visited);
  }
  if (expr.type === "group") {
    return referencesVariable(expr.expression, target, scope, visited);
  }
  if (expr.type === "offset") {
    return referencesVariable(expr.base, target, scope, visited);
  }
  if (expr.type === "call") {
    return expr.args.some((a) => referencesVariable(a.value, target, scope, visited));
  }
  return false;
}

// Flatten binary expressions into atomic terms
function flattenConditions(
  expr: PineExpr,
  scope: Map<string, PineExpr>,
  visited: Set<string> = new Set(),
): { terms: PineExpr[]; logic: "ALL" | "ANY"; isComplex: boolean } {
  let hasAnd = false;
  let hasOr = false;
  const terms: PineExpr[] = [];

  function walk(node: PineExpr) {
    if (node.type === "identifier" && scope.has(node.name)) {
      if (visited.has(node.name)) return;
      visited.add(node.name);
      const resolved = scope.get(node.name)!;
      walk(resolved);
      return;
    }

    if (node.type === "group") {
      walk(node.expression);
      return;
    }

    if (node.type === "binary") {
      if (node.operator === "and") {
        hasAnd = true;
        walk(node.left);
        walk(node.right);
        return;
      }
      if (node.operator === "or") {
        hasOr = true;
        walk(node.left);
        walk(node.right);
        return;
      }
    }

    terms.push(node);
  }

  walk(expr);

  const logic: "ALL" | "ANY" = hasOr && !hasAnd ? "ANY" : "ALL";
  const isComplex = hasAnd && hasOr;

  return { terms, logic, isComplex };
}

// Normalized Operand
type NormalizedOperand = {
  kind: "price" | "indicator" | "literal" | "benchmark" | "unknown";
  field?: string;
  period?: string;
  indicator?: string;
  indicatorPeriod?: string;
  value?: string | number;
  benchmarkSymbol?: string;
  label?: string;
};

function normalizeOperand(node: PineExpr, scope: Map<string, PineExpr>): NormalizedOperand {
  if (node.type === "group") {
    return normalizeOperand(node.expression, scope);
  }

  if (node.type === "identifier") {
    const rawName = node.name.toLowerCase();
    if (["close", "open", "high", "low", "volume"].includes(rawName)) {
      return { kind: "price", field: rawName.toUpperCase() };
    }
    if (scope.has(node.name)) {
      return normalizeOperand(scope.get(node.name)!, scope);
    }
    return { kind: "unknown", field: node.name };
  }

  if (node.type === "literal") {
    return { kind: "literal", value: node.value };
  }

  if (node.type === "offset") {
    const base = normalizeOperand(node.base, scope);
    if (base.kind === "price") {
      if (base.field === "HIGH" && node.offset === 1) {
        return { kind: "indicator", indicator: "HIGH", indicatorPeriod: "1" };
      }
      if (base.field === "LOW" && node.offset === 1) {
        return { kind: "indicator", indicator: "LOW", indicatorPeriod: "1" };
      }
      if (base.field === "CLOSE" && node.offset === 1) {
        return { kind: "indicator", indicator: "CLOSE", indicatorPeriod: "1" };
      }
      return { kind: "price", field: base.field };
    }
    if (base.kind === "indicator") {
      return base;
    }
    return base;
  }

  if (node.type === "call") {
    const callee = node.callee.toLowerCase();
    const args = node.args;

    // request.security(symbol, tf, expr) or security(...)
    if (callee === "request.security" || callee === "security") {
      const rawSym = args[0] ? resolveSymbolName(args[0].value, scope) : "NSE:NIFTY500";
      const sym = mapBenchmarkSymbol(rawSym);

      const innerExpr = args[2]?.value || args[args.length - 1]?.value;
      if (innerExpr) {
        const innerNorm = normalizeOperand(innerExpr, scope);
        if (innerNorm.kind === "indicator") {
          return {
            kind: "benchmark",
            benchmarkSymbol: sym,
            field: "BENCHMARK_CLOSE",
            indicator: innerNorm.indicator || "SMA",
            indicatorPeriod: innerNorm.indicatorPeriod || "50",
            label: `${sym} ${innerNorm.indicator || "SMA"} ${innerNorm.indicatorPeriod || "50"}`,
          };
        }
      }
      return {
        kind: "benchmark",
        benchmarkSymbol: sym,
        field: "BENCHMARK_CLOSE",
        label: `${sym} Close`,
      };
    }

    if (callee.startsWith("input") && args.length > 0) {
      const val = resolveInputDefault(node, scope);
      if (val != null) return { kind: "literal", value: val };
    }

    if (callee === "ta.sma" || callee === "sma") {
      const src = args[0] ? normalizeOperand(args[0].value, scope) : { field: "CLOSE" };
      const defaultPeriod = src.field === "VOLUME" ? 20 : 50;
      const periodVal = args[1] ? extractNumber(args[1].value, scope) : defaultPeriod;
      const period = String(periodVal || defaultPeriod);

      if (src.field === "VOLUME") {
        return { kind: "indicator", indicator: "AVG_VOLUME", indicatorPeriod: period };
      }
      return { kind: "indicator", indicator: "SMA", indicatorPeriod: period, field: "SMA", period };
    }

    if (callee === "ta.ema" || callee === "ema") {
      const periodVal = args[1] ? extractNumber(args[1].value, scope) : 20;
      const period = String(periodVal || 20);
      return { kind: "indicator", indicator: "EMA", indicatorPeriod: period, field: "EMA", period };
    }

    if (callee === "ta.wma" || callee === "wma") {
      const periodVal = args[1] ? extractNumber(args[1].value, scope) : 20;
      const period = String(periodVal || 20);
      return { kind: "indicator", indicator: "WMA", indicatorPeriod: period, field: "WMA", period };
    }

    if (callee === "ta.rsi" || callee === "rsi") {
      let periodVal = 14;
      if (args.length === 1) {
        periodVal = extractNumber(args[0].value, scope) || 14;
      } else if (args.length >= 2) {
        periodVal = extractNumber(args[1].value, scope) || 14;
      }
      const period = String(periodVal);
      return { kind: "indicator", indicator: "RSI", indicatorPeriod: period, field: "RSI", period };
    }

    if (callee === "ta.highest" || callee === "highest") {
      const periodVal = args.length >= 2 ? extractNumber(args[1].value, scope) : extractNumber(args[0].value, scope);
      const period = String(periodVal || 252);
      return { kind: "indicator", indicator: "HIGH", indicatorPeriod: period, field: "HIGH", period };
    }

    if (callee === "ta.lowest" || callee === "lowest") {
      const periodVal = args.length >= 2 ? extractNumber(args[1].value, scope) : extractNumber(args[0].value, scope);
      const period = String(periodVal || 252);
      return { kind: "indicator", indicator: "LOW", indicatorPeriod: period, field: "LOW", period };
    }
  }

  return { kind: "unknown" };
}

/**
 * Normalize a single term into a ModalBuilderFilter with semantic role classification.
 */
function normalizeTermToFilter(
  term: PineExpr,
  scope: Map<string, PineExpr>,
  idx: number,
  debugTrace: DebugTraceEntry[],
): ModalBuilderFilter | null {
  // Crossover function calls: ta.crossover(a, b), ta.crossunder(a, b)
  if (term.type === "call") {
    const callee = term.callee.toLowerCase();
    if (callee === "ta.crossover" || callee === "crossover" || callee === "ta.crossunder" || callee === "crossunder") {
      const op = callee.includes("crossunder") ? "cross_below" : "cross_above";
      const left = normalizeOperand(term.args[0]?.value, scope);
      const right = normalizeOperand(term.args[1]?.value, scope);

      const filter: ModalBuilderFilter = {
        id: `f_${idx}_${Date.now().toString(36)}`,
        field: left.field || "CLOSE",
        period: left.period,
        operator: op,
        rightKind: right.kind === "literal" ? "literal" : "indicator",
        literal: right.kind === "literal" ? String(right.value) : "",
        indicator: right.indicator || right.field || "SMA",
        indicatorPeriod: right.indicatorPeriod || right.period || "50",
        low: "",
        high: "",
        role: "ENTRY_FILTER",
      };

      debugTrace.push({
        expression: serializeExpr(term),
        resolved: `${filter.field} ${op} ${filter.indicator} ${filter.indicatorPeriod}`,
        role: "ENTRY_FILTER",
        builderField: `Entry Filter: ${filter.field} ${op} ${filter.indicator} ${filter.indicatorPeriod}`,
      });

      return filter;
    }
    return null;
  }

  // Binary comparison (>, <, >=, <=, ==, !=)
  if (term.type === "binary" && [">", "<", ">=", "<=", "==", "!="].includes(term.operator)) {
    const left = normalizeOperand(term.left, scope);
    const right = normalizeOperand(term.right, scope);

    if (left.kind === "unknown" && right.kind === "unknown") {
      return null;
    }

    let isBenchmark = false;
    let benchmarkSymbol = "NIFTY 500";
    let role: "ENTRY_FILTER" | "BENCHMARK_FILTER" = "ENTRY_FILTER";

    if (left.kind === "benchmark" || right.kind === "benchmark") {
      isBenchmark = true;
      benchmarkSymbol = left.benchmarkSymbol || right.benchmarkSymbol || "NIFTY 500";
      role = "BENCHMARK_FILTER";
    }

    let field = isBenchmark ? "BENCHMARK_CLOSE" : left.field || "CLOSE";
    let period = left.period;
    let operator = term.operator;
    let rightKind: "literal" | "indicator" = "indicator";
    let literal = "";
    let indicator = "SMA";
    let indicatorPeriod = "50";

    if (right.kind === "literal") {
      rightKind = "literal";
      literal = String(right.value);
      indicator = "";
      indicatorPeriod = "";
    } else {
      rightKind = "indicator";
      indicator = right.indicator || right.field || "SMA";
      const fallbackPeriod = indicator === "HIGH" || indicator === "LOW" ? "252" : indicator === "AVG_VOLUME" ? "20" : "50";
      indicatorPeriod = sanePeriod(right.indicatorPeriod || right.period, fallbackPeriod);
      literal = "";
    }

    if (!isBenchmark) {
      if (left.indicator === "SMA" && left.indicatorPeriod) {
        field = "SMA";
        period = left.indicatorPeriod;
      } else if (left.indicator === "EMA" && left.indicatorPeriod) {
        field = "EMA";
        period = left.indicatorPeriod;
      } else if (left.indicator === "RSI" && left.indicatorPeriod) {
        field = "RSI";
        period = left.indicatorPeriod;
      }
    }

    let label = `${field} ${operator} ${rightKind === "literal" ? literal : `${indicator} ${indicatorPeriod}`}`.trim();
    if (isBenchmark) {
      label = `${benchmarkSymbol} Close > ${benchmarkSymbol} SMA ${indicatorPeriod || 50}`;
    }

    const filter: ModalBuilderFilter = {
      id: `f_${idx}_${Date.now().toString(36)}`,
      field,
      period,
      operator,
      rightKind,
      literal,
      indicator,
      indicatorPeriod,
      low: "",
      high: "",
      role,
      isBenchmark,
      benchmarkSymbol: isBenchmark ? benchmarkSymbol : undefined,
      label,
    };

    debugTrace.push({
      expression: serializeExpr(term),
      resolved: label,
      role,
      builderField: `${role === "BENCHMARK_FILTER" ? "Benchmark Filter" : "Entry Filter"}: ${label}`,
    });

    return filter;
  }

  return null;
}

function getFilterSemanticKey(f: ModalBuilderFilter): string {
  if (f.isBenchmark || f.field === "BENCHMARK_CLOSE") {
    return `BENCHMARK:${f.benchmarkSymbol || "NIFTY500"}:${f.operator}:${f.indicator || "SMA"}:${f.indicatorPeriod || "50"}`;
  }
  return `${f.field}:${f.period || ""}:${f.operator}:${f.rightKind}:${f.literal}:${f.indicator || ""}:${f.indicatorPeriod || ""}`;
}

// Helpers
function sanePeriod(raw: string | number | null | undefined, fallback: string): string {
  if (raw == null || raw === "" || raw === "null" || raw === "undefined") return fallback;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return String(n);
}

function isInputCall(node: PineExpr): boolean {
  return node.type === "call" && node.callee.toLowerCase().startsWith("input");
}

function inputDefaultArg(node: PineExpr): PineExpr | undefined {
  if (node.type !== "call") return undefined;
  return node.args.find((a) => a.name === "defval")?.value ?? node.args[0]?.value;
}

function resolveInputDefault(node: PineExpr, scope: Map<string, PineExpr>, visited: Set<string> = new Set()): any {
  const defval = inputDefaultArg(node);
  return defval ? resolveConstant(defval, scope, visited) : null;
}

function extractNumber(node: PineExpr, scope: Map<string, PineExpr>, visited: Set<string> = new Set()): number | null {
  if (node.type === "literal" && typeof node.value === "number") return node.value;
  if (node.type === "group") return extractNumber(node.expression, scope, visited);
  if (node.type === "offset") return extractNumber(node.base, scope, visited);
  if (node.type === "unary" && node.operator === "-") {
    const v = extractNumber(node.argument, scope, visited);
    return v != null ? -v : null;
  }
  if (node.type === "identifier") {
    if (visited.has(node.name) || !scope.has(node.name)) return null;
    visited.add(node.name);
    return extractNumber(scope.get(node.name)!, scope, visited);
  }
  if (isInputCall(node)) {
    const defval = inputDefaultArg(node);
    return defval ? extractNumber(defval, scope, visited) : null;
  }
  return null;
}

function resolveConstant(node: PineExpr, scope: Map<string, PineExpr>, visited: Set<string> = new Set()): any {
  if (node.type === "literal") return node.value;
  if (node.type === "group") return resolveConstant(node.expression, scope, visited);
  if (node.type === "identifier") {
    if (visited.has(node.name) || !scope.has(node.name)) return null;
    visited.add(node.name);
    return resolveConstant(scope.get(node.name)!, scope, visited);
  }
  if (isInputCall(node)) {
    return resolveInputDefault(node, scope, visited);
  }
  return null;
}

function resolveSymbolName(node: PineExpr, scope: Map<string, PineExpr>): string {
  const resolved = resolveConstant(node, scope);
  if (typeof resolved === "string" && resolved.trim()) return resolved;
  return serializeExpr(node).replace(/['"]/g, "");
}

function mapBenchmarkSymbol(raw: string): string {
  const u = String(raw || "").toUpperCase().replace(/['"]/g, "").replace(/\s+/g, "");
  if (u.includes("CNX500") || u.includes("NIFTY500") || u.includes("NIFTY_500")) return "NIFTY 500";
  if ((u.includes("NIFTY50") || u.includes("CNX50") || u.includes("NIFTY_50")) && !u.includes("NIFTY500")) return "NIFTY 50";
  return raw.replace(/['"]/g, "") || "NIFTY 500";
}

function extractMultiplier(node: PineExpr, scope: Map<string, PineExpr>): number | null {
  if (node.type === "binary") {
    if (node.operator === "*") {
      const l = extractNumber(node.left, scope);
      if (l != null) return l;
      const r = extractNumber(node.right, scope);
      if (r != null) return r;
    }
    const leftMult = extractMultiplier(node.left, scope);
    if (leftMult != null) return leftMult;
    const rightMult = extractMultiplier(node.right, scope);
    if (rightMult != null) return rightMult;
  }
  return null;
}

function serializeExpr(node: PineExpr): string {
  if (!node) return "";
  if (node.type === "literal") return String(node.value);
  if (node.type === "identifier") return node.name;
  if (node.type === "offset") return `${serializeExpr(node.base)}[${node.offset}]`;
  if (node.type === "group") return `(${serializeExpr(node.expression)})`;
  if (node.type === "unary") return `${node.operator} ${serializeExpr(node.argument)}`;
  if (node.type === "binary") return `${serializeExpr(node.left)} ${node.operator} ${serializeExpr(node.right)}`;
  if (node.type === "call") {
    const argsStr = node.args.map((a) => (a.name ? `${a.name}=${serializeExpr(a.value)}` : serializeExpr(a.value))).join(", ");
    return `${node.callee}(${argsStr})`;
  }
  if (node.type === "unsupported") return node.text;
  return "";
}
