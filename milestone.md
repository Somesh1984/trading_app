M1: Runtime Stabilization

Goal:
Current project ko clean, predictable aur repeatable run state me lana.

Isme kya aayega:

imports cleanup
duplicate/unused modules identify karna
main.py flow ko stable banana
config validation ko strict karna
basic logging improve karna





M2: Historical + Live Continuity

Goal:
Historical candles aur live websocket candles ke beech koi gap na rahe.

Isme kya aayega:

startup warmup ko harden karna
partial/live candle handling
last closed candle continuity
reconnect ke baad missing candle recovery
sequential candle stream maintain karna



M3: State Persistence

Goal:
App restart ya websocket break ke baad bhi minimum required state recover ho sake.

Isme kya aayega:

latest tick/state save
latest closed candles save
open paper trades state save
restart par restore logic
parquet/state storage ko runner me integrate karna




M4: Symbol Universe Management

Goal:
Live subscribed symbols ko controlled aur reliable tarike se manage karna.

Isme kya aayega:

spot/index tracking
ATM/OTM/ITM option selection
dynamic resubscription
new symbol historical backfill
symbols.py vs symbol_pd.py responsibility clear karna



M5: Candle Engine Hardening

Goal:
Candle builder ko robust banana taki market timing edge cases me bhi sahi kaam kare.

Isme kya aayega:

bucket alignment
market open handling
mid-candle app start
websocket reconnect edge cases
different timeframes support ka clean base




M6: Strategy Pipeline Cleanup

Goal:
Signal generation flow ko clean service pattern me lana.

Isme kya aayega:

strategy input/output standardize karna
candle to signal pipeline simplify karna
breakout strategy ko isolate karna
future strategies ke liye reusable interface banana




M7: Paper Trading Engine Completion

Goal:
Paper execution ko reliable testing engine banana.

Isme kya aayega:

entry/exit flow harden karna
reverse signal handling verify karna
SL/TP handling improve karna
realized/unrealized/portfolio PnL validation
trade lifecycle reporting




M8: PNF Integration

Goal:
Existing PNF engine ko live market pipeline ke saath connect karna.

Isme kya aayega:

candle feed to PNF service
PNF chart state update
PNF signal extraction
runner me PNF hook
PNF aur execution ke beech interface define karna




M9: Order Flow Readiness

Goal:
Paper se real broker order flow ki taraf clean transition ka base banana.

Isme kya aayega:

place/cancel wrapper verification
order response normalization
order websocket readiness
broker execution interface
paper/live execution separation




M10: Positions, Holdings, Reporting

Goal:
Account-level broker data ko execution layer ke saath align karna.

Isme kya aayega:

positions fetch
holdings fetch
orderbook integration
state display/reporting
reconciliation helpers




M11: Production Safety Layer

Goal:
System ko accidental bad behavior se bachana.

Isme kya aayega:

duplicate signal protection
duplicate order guard
reconnect safety
symbol validation
trading hour checks
fail-safe exits/logging




M12: Cleanup, Refactor, Tests

Goal:
Working prototype ko maintainable project me convert karna.

Isme kya aayega:

folder/module cleanup
duplicate code remove
naming consistency
manual test scripts
basic unit tests
final documentation
Recommended order

Aapke current project ke liye best sequence ye hai:

M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M12

Sabse immediate important milestones

Agar priority basis par dekhen to pehle ye 4 sabse important hain:

M1 Runtime Stabilization
M2 Historical + Live Continuity
M3 State Persistence
M5 Candle Engine Hardening