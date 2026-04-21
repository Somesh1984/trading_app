Updated Milestones till Paper Trading
M1: Runtime Stabilization

Goal: project ko clean aur repeatable run state me lana 
Include:

imports cleanup
config/env validation
main.py flow stable
basic run verification

Ye current base milestone rahega.


===============================================================
M2: Broker Core Completion

Goal: FYERS broker layer ko usable banana
Include:

auth/login stable
profile fetch
history fetch
basic broker wrapper methods
response normalization


=================================================================
M3: Live Market Stream

Goal: websocket se clean live tick stream lena
Include:

websocket connect
subscribed symbols se ticks receive
tick parsing
broker → app tick flow

===================================================================

M4: Historical + Live Continuity

Goal: historical aur websocket data ke beech gap na rahe
Include:

startup historical warmup
last closed candle continuity
partial/live candle handling
startup gap bridging

Ye bahut important hai, aapke current stage ke hisaab se bhi.

====================================================================

M5: Candle Engine Completion

Goal: ticks se reliable candles banana
Include:

5s candle build
1m candle build
candle close event
bucket alignment
mid-candle app start handling

====================================================================

M6: Strategy Input Pipeline

Goal: candle output ko strategy/analysis layer tak clean bhejna
Include:

candle callback flow
symbol-wise routing
strategy input structure
main.py me pipeline connect karna

===================================================================

M7: Paper Trading Engine Completion

Goal: signal se paper trade lifecycle chalana
Include:

entry flow
exit flow
reverse signal handling
realized/unrealized pnl
closed trades tracking
portfolio pnl reporting

Ye paper trading tak ka main milestone hai.


===================================================================

Optional before paper trading complete bolna
M8: Basic Account Data Readiness

Goal: broker side supporting reads available ho
Include:

positions fetch
holdings fetch
orderbook fetch
normalized display

Ye helpful hai, but paper trading ke liye mandatory nahi.


