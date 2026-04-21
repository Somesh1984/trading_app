# Trading App - Issues (Paper Trading Roadmap)

---

## M4: Historical + Live Continuity

### M4.1 Startup historical warmup

**Objective:** startup par recent historical candles load karna
**Scope:** broker history fetch, candle manager seed
**Acceptance Criteria:**

* websocket se pehle historical load ho
* startup par recent candles available ho
  **Test:**
* app run → historical count print
* candles gap ke bina continue

---

### M4.2 Last closed candle continuity & duplicate handling

**Objective:** historical + live continuity maintain karna
**Scope:** overlap removal, timestamp validation
**Acceptance Criteria:**

* duplicate candles na ho
* timestamps increasing ho
  **Test:**
* mid-start → sequence check

---

### M4.3 Partial candle reconstruction (mid-start)

**Objective:** mid-candle start par correct candle banana
**Scope:** current bucket reconstruction
**Acceptance Criteria:**

* first candle distorted na ho
  **Test:**
* random second start → OHLC verify

---

## M5: Candle Engine Completion

### M5.1 5s candle correctness

**Objective:** accurate OHLC
**Scope:** tick → candle mapping
**Acceptance Criteria:**

* OHLC correct ho
  **Test:**
* manual tick vs candle compare

---

### M5.2 1m candle aggregation

**Objective:** 5s → 1m aggregation
**Scope:** 12 candles combine
**Acceptance Criteria:**

* 1m OHLC correct
  **Test:**
* 12×5s vs 1m compare

---

### M5.3 Bucket alignment

**Objective:** time boundary correct karna
**Scope:** epoch alignment
**Acceptance Criteria:**

* candles exact boundaries par close
  **Test:**
* random start → same alignment

---

## M6: Strategy Input Pipeline

### M6.1 Candle callback

**Objective:** candle → strategy flow
**Scope:** callback interface
**Acceptance Criteria:**

* candle close par callback trigger
  **Test:**
* log print on close

---

### M6.2 Symbol-wise routing

**Objective:** multi-symbol isolation
**Scope:** per-symbol processing
**Acceptance Criteria:**

* data mix na ho
  **Test:**
* 2 symbols verify

---

### M6.3 Input standardization

**Objective:** fixed candle model
**Scope:** dataclass define
**Acceptance Criteria:**

* consistent structure
  **Test:**
* sample object pass

---

## M7: Paper Trading Engine

### M7.1 Strategy → paper engine

**Objective:** signal integration
**Scope:** BUY/SELL flow
**Acceptance Criteria:**

* signal → trade execute
  **Test:**
* dummy signal run

---

### M7.2 Reverse signal handling

**Objective:** trade switching
**Scope:** close + open logic
**Acceptance Criteria:**

* single active trade
  **Test:**
* BUY → SELL → BUY

---

### M7.3 PnL validation

**Objective:** correct pnl calculation
**Scope:** realized/unrealized
**Acceptance Criteria:**

* pnl accurate
  **Test:**
* manual vs system compare

---

### M7.4 Trade lifecycle reporting

**Objective:** visibility improve
**Scope:** logs + summary
**Acceptance Criteria:**

* open/close logs visible
  **Test:**
* trade sequence verify

---

## Execution Order

1. M4 (Continuity)
2. M5 (Candle correctness)
3. M6 (Pipeline)
4. M7 (Execution)

---
