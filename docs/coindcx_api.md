# CoinDCX API

**Base REST URL:** `https://api.coindcx.com`

Each section opens with a brief description of what the category covers and when to use it, followed by its full endpoint reference.

---

## Table of Contents

- [Authentication](#authentication)
- [Error Codes](#error-codes)
- [Rate Limits](#rate-limits)
- [Public / Market Data APIs](#public--market-data-apis)
  - [GET /exchange/ticker](#get-exchangeticker)
  - [GET /exchange/v1/markets](#get-exchangev1markets)
  - [GET /exchange/v1/markets_details](#get-exchangev1markets_details)
  - [GET /market_data/trade_history](#get-market_datatrade_history)
  - [GET /market_data/orderbook](#get-market_dataorderbook)
  - [GET /market_data/candles](#get-market_datacandles)
- [User APIs](#user-apis)
  - [POST /exchange/v1/users/balances](#post-exchangev1usersbalances)
  - [POST /exchange/v1/users/info](#post-exchangev1usersinfo)
- [Spot Trading APIs](#spot-trading-apis)
  - [POST /exchange/v1/orders/create](#post-exchangev1orderscreate)
  - [POST /exchange/v1/orders/create_multiple](#post-exchangev1orderscreate_multiple)
  - [POST /exchange/v1/orders/status](#post-exchangev1ordersstatus)
  - [POST /exchange/v1/orders/status_multiple](#post-exchangev1ordersstatus_multiple)
  - [POST /exchange/v1/orders/active_orders](#post-exchangev1ordersactive_orders)
  - [POST /exchange/v1/orders/active_orders_count](#post-exchangev1ordersactive_orders_count)
  - [POST /exchange/v1/orders/trade_history](#post-exchangev1orderstrade_history)
  - [POST /exchange/v1/orders/edit](#post-exchangev1ordersedit)
  - [POST /exchange/v1/orders/cancel](#post-exchangev1orderscancel)
  - [POST /exchange/v1/orders/cancel_by_ids](#post-exchangev1orderscancel_by_ids)
  - [POST /exchange/v1/orders/cancel_all](#post-exchangev1orderscancel_all)
- [Margin Trading APIs](#margin-trading-apis)
  - [POST /exchange/v1/margin/orders/create](#post-exchangev1marginorderscreate)
  - [POST /exchange/v1/margin/orders/cancel](#post-exchangev1marginorderscancel)
  - [POST /exchange/v1/margin/orders/exit](#post-exchangev1marginordersexit)
  - [POST /exchange/v1/margin/orders/edit_target](#post-exchangev1marginordersedit_target)
  - [POST /exchange/v1/margin/orders/edit_sl](#post-exchangev1marginordersedit_sl)
  - [POST /exchange/v1/margin/orders/add_margin](#post-exchangev1marginordersadd_margin)
  - [POST /exchange/v1/margin/orders/remove_margin](#post-exchangev1marginordersremove_margin)
  - [POST /exchange/v1/margin/orders/list](#post-exchangev1marginorderslist)
  - [POST /exchange/v1/margin/orders/status](#post-exchangev1marginordersstatus)
- [Lend APIs](#lend-apis)
  - [POST /exchange/v1/funding/lend](#post-exchangev1fundinglend)
  - [POST /exchange/v1/funding/settle](#post-exchangev1fundingsettle)
  - [POST /exchange/v1/funding/fetch_orders](#post-exchangev1fundingfetch_orders)
- [Futures APIs](#futures-apis)
  - [Futures Market Data (Public)](#futures-market-data-public)
  - [POST /exchange/v1/futures/orders/create](#post-exchangev1futuresorderscreate)
  - [POST /exchange/v1/futures/orders/cancel](#post-exchangev1futuresorderscancel)
  - [POST /exchange/v1/futures/orders/cancel_all](#post-exchangev1futuresorderscancel_all)
  - [POST /exchange/v1/futures/orders/list](#post-exchangev1futuresorderslist)
  - [POST /exchange/v1/futures/positions/list](#post-exchangev1futurespositionslist)
  - [POST /exchange/v1/futures/positions/exit](#post-exchangev1futurespositionsexit)
  - [POST /exchange/v1/futures/positions/add_margin](#post-exchangev1futurespositionsadd_margin)
  - [POST /exchange/v1/futures/positions/remove_margin](#post-exchangev1futurespositionsremove_margin)
  - [POST /exchange/v1/futures/tpsl/create](#post-exchangev1futurestpslcreate)
  - [POST /exchange/v1/futures/wallet/transfer](#post-exchangev1futureswallettransfer)
  - [POST /exchange/v1/futures/wallet/details](#post-exchangev1futureswalletdetails)
- [Wallet & Transfer APIs](#wallet--transfer-apis)
  - [POST /exchange/v1/wallets/transfer](#post-exchangev1walletstransfer)
  - [POST /exchange/v1/wallets/sub_account_transfer](#post-exchangev1walletssub_account_transfer)
- [Spot WebSockets](#spot-websockets)
- [Futures WebSockets](#futures-websockets)

---

## Authentication

All private endpoints require two HTTP headers and a `timestamp` field in the JSON body. Public endpoints require no authentication.

**Use when:** Any call to a private endpoint (User, Spot, Margin, Futures, Lend, Wallet).

### Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-AUTH-APIKEY` | Your API key from the CoinDCX dashboard |
| `X-AUTH-SIGNATURE` | HMAC-SHA256 hex digest of the JSON-serialized request body |

### Signature Generation

```python
import hmac, hashlib, json, time

secret = b"your_api_secret"
payload = {"timestamp": int(time.time() * 1000)}
body = json.dumps(payload, separators=(',', ':'))
signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
```

```javascript
const crypto = require('crypto');
const payload = { timestamp: Date.now() };
const body = JSON.stringify(payload);
const signature = crypto.createHmac('sha256', apiSecret).update(body).digest('hex');
```

### Rules

- `timestamp` must be the current Unix time in **milliseconds**
- The server rejects requests with timestamps too far from server time
- Every request must be freshly signed — signatures cannot be reused

---

## Error Codes

| HTTP Status | Meaning | Common Cause |
|---|---|---|
| `200` | Success | Request processed |
| `400` | Bad Request | Missing or invalid parameter, invalid market |
| `401` | Unauthorized | Missing, invalid, or incorrectly signed API key |
| `404` | Not Found | Order, position, or resource does not exist |
| `422` | Unprocessable | Insufficient funds, unverified account, business rule violation |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Server Error | CoinDCX internal error |

**Error response body:**
```json
{ "error": "Insufficient funds", "code": 422 }
```

---

## Rate Limits

| Endpoint | Limit |
|---|---|
| Create order | 2000 / 60s |
| Create multiple orders | 2000 / 60s |
| Order status | 2000 / 60s |
| Edit order | 2000 / 60s |
| Cancel (single) | 2000 / 60s |
| Cancel multiple by IDs | 300 / 60s |
| Active orders | 300 / 60s |
| Cancel all | 30 / 60s |

---

## Public / Market Data APIs

No authentication required. Data is read-only and open to anyone.

**Covers:** ticker prices, order book depth, recent trade history, candlestick data, and market pair specifications.

**Use when:** Building price displays, market screeners, backtesting pipelines, or any application that only needs market data without placing orders.

---

### GET /exchange/ticker

Returns a snapshot of all market tickers.

```
GET https://api.coindcx.com/exchange/ticker
```

No parameters.

**Sample request**
```python
import requests
response = requests.get("https://api.coindcx.com/exchange/ticker")
data = response.json()
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `market` | string | Market identifier (e.g. `BTCUSDT`) |
| `change_24_hour` | string | 24h price change percentage |
| `high` | string | 24h high price |
| `low` | string | 24h low price |
| `volume` | string | 24h trading volume |
| `last_price` | string | Last traded price |
| `bid` | string | Best bid price |
| `ask` | string | Best ask price |
| `timestamp` | number | Snapshot time in Unix ms |

**Sample response**
```json
[
  {
    "market": "BTCUSDT",
    "change_24_hour": "-1.621",
    "high": "45200.00",
    "low": "43800.00",
    "volume": "1240.55",
    "last_price": "44600.00",
    "bid": "44595.00",
    "ask": "44605.00",
    "timestamp": 1783424912907
  }
]
```

---

### GET /exchange/v1/markets

Returns a list of all active market names.

```
GET https://api.coindcx.com/exchange/v1/markets
```

No parameters.

**Sample response**
```json
["BTCUSDT", "ETHUSDT", "XTZBTC", "SNTBTC"]
```

---

### GET /exchange/v1/markets_details

Returns full trading specifications for all markets.

```
GET https://api.coindcx.com/exchange/v1/markets_details
```

No parameters.

**Response fields**

| Field | Type | Description |
|---|---|---|
| `coindcx_name` | string | Internal market name |
| `symbol` | string | Trading pair symbol |
| `pair` | string | Pair in exchange format (e.g. `B-BTC_USDT`) |
| `ecode` | string | Exchange code (`B`, `I`, `KC`) |
| `base_currency_short_name` | string | Base currency (e.g. `USDT`) |
| `target_currency_short_name` | string | Target/quote currency (e.g. `BTC`) |
| `base_currency_precision` | number | Decimal places for base currency |
| `target_currency_precision` | number | Decimal places for target currency |
| `min_quantity` | number | Minimum order quantity |
| `max_quantity` | number | Maximum order quantity |
| `min_price` | number | Minimum price allowed |
| `max_price` | number | Maximum price allowed |
| `min_notional` | number | Minimum order value in base currency |
| `step` | number | Quantity increment step |
| `order_types` | array | Supported order types |
| `status` | string | Market status (`active`, `suspended`) |

**Sample response**
```json
[
  {
    "coindcx_name": "BTCUSDT",
    "base_currency_short_name": "USDT",
    "target_currency_short_name": "BTC",
    "target_currency_name": "Bitcoin",
    "base_currency_name": "Tether",
    "base_currency_precision": 2,
    "target_currency_precision": 8,
    "min_quantity": 0.0001,
    "max_quantity": 90000000,
    "min_price": 1e-8,
    "max_price": 1000000,
    "min_notional": 10,
    "step": 0.0001,
    "order_types": ["limit_order", "market_order", "stop_limit"],
    "symbol": "BTCUSDT",
    "ecode": "B",
    "pair": "B-BTC_USDT",
    "status": "active"
  }
]
```

---

### GET /market_data/trade_history

Returns recent public trades for a market.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pair` | string | Yes | Pair identifier from markets_details (e.g. `B-BTC_USDT`) |
| `limit` | integer | No | Number of trades. Default `30`, max `500` |

**Sample request**
```
GET https://api.coindcx.com/market_data/trade_history?pair=B-BTC_USDT&limit=5
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `p` | number | Trade price |
| `q` | number | Trade quantity |
| `s` | string | Symbol |
| `T` | number | Trade timestamp in Unix ms |
| `m` | boolean | `true` if buyer was the maker |

**Sample response**
```json
[
  {
    "p": 44600.00,
    "q": 0.023519,
    "s": "BTCUSDT",
    "T": 1565163305770,
    "m": false
  }
]
```

---

### GET /market_data/orderbook

Returns the current order book for a market.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pair` | string | Yes | Pair identifier (e.g. `B-BTC_USDT`) |
| `depth` | integer | No | Depth levels. Valid: `1`, `5`, `10`, `20`, `50`, `100`, `200`. Default `50` |

**Sample request**
```
GET https://api.coindcx.com/market_data/orderbook?pair=B-BTC_USDT&depth=10
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `timestamp` | number | Snapshot time in Unix ms |
| `bids` | object | Price → quantity map for buy orders |
| `asks` | object | Price → quantity map for sell orders |

**Sample response**
```json
{
  "timestamp": 1783425132686,
  "bids": {
    "44590.00000000": "0.152300",
    "44585.00000000": "0.430100"
  },
  "asks": {
    "44605.00000000": "0.089400",
    "44610.00000000": "0.220000"
  }
}
```

---

### GET /market_data/candles

Returns OHLCV candlestick data for a market.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pair` | string | Yes | Pair identifier |
| `interval` | string | Yes | Candle interval: `1m`, `15m`, `1h`, `1d` |
| `startTime` | integer | No | Start time in Unix ms |
| `endTime` | integer | No | End time in Unix ms |
| `limit` | integer | No | Number of candles. Default `500`, max `1000` |

**Sample request**
```
GET https://api.coindcx.com/market_data/candles?pair=B-BTC_USDT&interval=1h&limit=24
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `open` | number | Opening price |
| `high` | number | High price |
| `low` | number | Low price |
| `close` | number | Closing price |
| `volume` | number | Volume traded in the interval |
| `time` | number | Candle open time in Unix ms |

**Sample response**
```json
[
  {
    "open": 44200.00,
    "high": 44800.00,
    "low": 44100.00,
    "close": 44600.00,
    "volume": 312.45,
    "time": 1783422000000
  }
]
```

---

## User APIs

Authentication required. Provides account-level information for the authenticated user.

**Covers:** account balances across all currencies and user profile metadata.

**Use when:** Displaying portfolio balances, checking available funds before placing orders, or verifying account state.

---

### POST /exchange/v1/users/balances

Returns balances for all currencies in the authenticated account.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request**
```python
import hmac, hashlib, json, time, requests

secret = b"your_api_secret"
payload = {"timestamp": int(time.time() * 1000)}
body = json.dumps(payload, separators=(',', ':'))
signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()

response = requests.post(
    "https://api.coindcx.com/exchange/v1/users/balances",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": "your_api_key",
        "X-AUTH-SIGNATURE": signature
    }
)
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `currency` | string | Asset symbol |
| `balance` | number | Available (unlocked) balance |
| `locked_balance` | number | Balance reserved in open orders |

**Sample response**
```json
[
  { "currency": "BTC", "balance": 0.5432, "locked_balance": 0.1000 },
  { "currency": "USDT", "balance": 5000.50, "locked_balance": 1200.00 }
]
```

---

### POST /exchange/v1/users/info

Returns profile information for the authenticated user.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `coindcx_id` | string | Internal user UUID |
| `first_name` | string | First name |
| `last_name` | string | Last name |
| `mobile_number` | string | Registered phone number |
| `email` | string | Registered email address |

**Sample response**
```json
[
  {
    "coindcx_id": "fda259ce-22fc-11e9-ba72-ef9b29b5db2b",
    "first_name": "John",
    "last_name": "Doe",
    "mobile_number": "9876543210",
    "email": "[email protected]"
  }
]
```

---

## Spot Trading APIs

Authentication required. Core trading functionality for the spot market.

**Covers:** placing market and limit orders, cancelling orders, querying order status, listing active orders, and retrieving trade history.

**Use when:** Executing buy/sell orders at current market prices or at a specified limit price, without leverage.

**Order status values:** `init`, `open`, `partially_filled`, `filled`, `cancelled`, `rejected`, `partially_cancelled`, `untriggered`

---

### POST /exchange/v1/orders/create

Places a new spot order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `market` | string | Yes | Trading pair symbol (e.g. `BTCUSDT`) |
| `side` | string | Yes | `buy` or `sell` |
| `order_type` | string | Yes | `market_order` or `limit_order` |
| `total_quantity` | number | Yes | Quantity of the target currency to trade |
| `price_per_unit` | number | Limit only | Price per unit in base currency |
| `client_order_id` | string | No | Your own unique order identifier |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "market": "BTCUSDT",
  "side": "buy",
  "order_type": "limit_order",
  "total_quantity": 0.5,
  "price_per_unit": 44500.00,
  "client_order_id": "my-order-001",
  "timestamp": 1524211224000
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | CoinDCX order ID |
| `client_order_id` | string | Your custom order ID |
| `market` | string | Market the order was placed on |
| `order_type` | string | Order type |
| `side` | string | `buy` or `sell` |
| `status` | string | Current order status |
| `total_quantity` | number | Original order quantity |
| `remaining_quantity` | number | Unfilled quantity |
| `avg_price` | number | Average fill price (0 if unfilled) |
| `price_per_unit` | number | Requested limit price |
| `fee` | number | Fee rate percentage |
| `fee_amount` | number | Fee charged so far |
| `maker_fee` | number | Maker fee rate |
| `taker_fee` | number | Taker fee rate |
| `time_in_force` | string | `good_till_cancel` or `immediate_or_cancel` |
| `stop_price` | number | Stop trigger price (0 if none) |
| `created_at` | number | Order creation time in Unix ms |
| `updated_at` | number | Last update time in Unix ms |
| `source` | string | Order source (`api`, `web`, `app`) |

**Sample response**
```json
{
  "orders": [
    {
      "id": "815052513",
      "client_order_id": "my-order-001",
      "market": "BTCUSDT",
      "order_type": "limit_order",
      "side": "buy",
      "status": "open",
      "fee_amount": 0,
      "fee": 0.1,
      "maker_fee": 0.1,
      "taker_fee": 0.1,
      "total_quantity": 0.5,
      "remaining_quantity": 0.5,
      "avg_price": 0,
      "price_per_unit": 44500.00,
      "time_in_force": "good_till_cancel",
      "stop_price": 0,
      "created_at": 1783421549770,
      "updated_at": 1783421549841,
      "source": "api"
    }
  ]
}
```

**Error responses**
```json
{ "error": "Invalid market", "code": 400 }
{ "error": "Insufficient funds", "code": 422 }
```

---

### POST /exchange/v1/orders/create_multiple

Places up to 10 orders in a single request.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `orders` | array | Yes | Array of order objects (max 10). Each object accepts the same fields as `/orders/create` |

**Sample request body**
```json
{
  "orders": [
    {
      "market": "BTCUSDT", "side": "buy", "order_type": "limit_order",
      "total_quantity": 0.1, "price_per_unit": 44000.00, "timestamp": 1524211224000
    },
    {
      "market": "BTCUSDT", "side": "buy", "order_type": "limit_order",
      "total_quantity": 0.1, "price_per_unit": 43500.00, "timestamp": 1524211224000
    }
  ]
}
```

**Sample response**
```json
{
  "orders": [
    { "id": "815052514", "status": "open", "market": "BTCUSDT", "side": "buy", "price_per_unit": 44000.00 },
    { "id": "815052515", "status": "open", "market": "BTCUSDT", "side": "buy", "price_per_unit": 43500.00 }
  ]
}
```

---

### POST /exchange/v1/orders/status

Retrieves the status of a single order. Provide either `id` or `client_order_id`.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Conditional | CoinDCX order ID |
| `client_order_id` | string | Conditional | Your custom order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "815052513", "timestamp": 1524211224000 }
```

**Sample response**
```json
{
  "id": "815052513",
  "client_order_id": "my-order-001",
  "market": "BTCUSDT",
  "order_type": "limit_order",
  "side": "buy",
  "status": "partially_filled",
  "total_quantity": 0.5,
  "remaining_quantity": 0.3,
  "avg_price": 44500.00,
  "price_per_unit": 44500.00,
  "fee_amount": 0.022,
  "created_at": 1783421549770,
  "updated_at": 1783421612000
}
```

**Error response**
```json
{ "error": "Order not found", "code": 404 }
```

---

### POST /exchange/v1/orders/status_multiple

Retrieves the status of up to 10 orders. Provide either `ids` or `client_order_ids`.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ids` | array | Conditional | Array of CoinDCX order IDs (max 10) |
| `client_order_ids` | array | Conditional | Array of custom order IDs (max 10) |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "ids": ["815052513", "815052514"], "timestamp": 1524211224000 }
```

**Sample response**
```json
[
  { "id": "815052513", "status": "filled", "avg_price": 44500.00 },
  { "id": "815052514", "status": "open", "avg_price": 0 }
]
```

---

### POST /exchange/v1/orders/active_orders

Returns all open and partially filled orders for a market.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `market` | string | Yes | Trading pair |
| `side` | string | No | Filter by `buy` or `sell` |
| `page` | integer | No | Page number. Default `1` |
| `size` | integer | No | Records per page. Default/max `200` |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "market": "BTCUSDT", "side": "buy", "page": 1, "size": 50, "timestamp": 1524211224000 }
```

**Sample response**
```json
{
  "orders": [
    {
      "id": "815052513",
      "user_id": "16248266",
      "client_order_id": "my-order-001",
      "market": "BTCUSDT",
      "order_type": "limit_order",
      "side": "buy",
      "status": "open",
      "total_quantity": 0.5,
      "remaining_quantity": 0.5,
      "avg_price": 0,
      "price_per_unit": 44500.00,
      "fee_amount": 0,
      "fee": 0.1,
      "maker_fee": 0.1,
      "taker_fee": 0.1,
      "ecode": "B",
      "created_at": "2026-09-10T10:52:29.770Z",
      "updated_at": "2026-09-10T10:52:29.841Z",
      "market_order_locked": 22250,
      "locked_spot_balance": true
    }
  ]
}
```

---

### POST /exchange/v1/orders/active_orders_count

Returns the count of active orders for a market.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `market` | string | Yes | Trading pair |
| `side` | string | No | Filter by `buy` or `sell` |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "market": "BTCUSDT", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "count": 7 }
```

---

### POST /exchange/v1/orders/trade_history

Returns the authenticated user's executed trades.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |
| `limit` | integer | No | Number of records. Default/max `500` |
| `sort` | string | No | `asc` or `desc` |
| `from_id` | integer | No | Return trades with ID greater than this |
| `from_timestamp` | integer | No | Start time in Unix ms |
| `to_timestamp` | integer | No | End time in Unix ms |
| `symbol` | string | No | Filter by market (e.g. `BTCUSDT`) |

**Sample request body**
```json
{ "limit": 100, "sort": "desc", "symbol": "BTCUSDT", "timestamp": 1524211224000 }
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `id` | number | Trade ID |
| `order_id` | string | Associated order ID |
| `side` | string | `buy` or `sell` |
| `quantity` | number | Quantity traded |
| `price` | number | Execution price |
| `fee_amount` | number | Fee charged |
| `symbol` | string | Market symbol |
| `ecode` | string | Exchange code |
| `timestamp` | number | Trade time in Unix ms |

**Sample response**
```json
[
  {
    "id": 252949810,
    "order_id": "815052513",
    "side": "buy",
    "quantity": 0.2,
    "price": 44500.00,
    "fee_amount": 0.0089,
    "symbol": "BTCUSDT",
    "ecode": "B",
    "timestamp": 1780415747836
  }
]
```

---

### POST /exchange/v1/orders/edit

Edits the price of an existing open order. Provide either `id` or `client_order_id`.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Conditional | CoinDCX order ID |
| `client_order_id` | string | Conditional | Your custom order ID |
| `price_per_unit` | number | Yes | New limit price |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "815052513", "price_per_unit": 44200.00, "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "id": "815052513", "status": "open", "price_per_unit": 44200.00, "updated_at": 1783421700000 }
```

---

### POST /exchange/v1/orders/cancel

Cancels a single order. Provide either `id` or `client_order_id`.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Conditional | CoinDCX order ID |
| `client_order_id` | string | Conditional | Your custom order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "815052513", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "message": "success", "status": "success", "code": 200 }
```

**Error response**
```json
{ "error": "Order not found", "code": 404 }
```

---

### POST /exchange/v1/orders/cancel_by_ids

Cancels up to 10 orders by ID. Provide either `ids` or `client_order_ids`.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ids` | array | Conditional | Array of CoinDCX order IDs (max 10) |
| `client_order_ids` | array | Conditional | Array of custom order IDs (max 10) |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "ids": ["815052513", "815052514", "815052515"], "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "message": "success", "code": 200 }
```

---

### POST /exchange/v1/orders/cancel_all

Cancels all open orders for a market.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `market` | string | Yes | Trading pair |
| `side` | string | No | Cancel only `buy` or only `sell` orders |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "market": "BTCUSDT", "side": "buy", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "message": "success", "code": 200 }
```

---

## Margin Trading APIs

Authentication required. Leveraged trading using bracket orders with built-in risk controls.

**Covers:** placing leveraged bracket orders (entry + target + stop-loss in one request), modifying target and stop-loss levels, adding/removing collateral, and exiting positions.

**Use when:** Trading with borrowed capital and needing predefined profit targets and stop-loss levels enforced at the order level. Suited for intraday leveraged trades on the spot market.

**Order status values:** `init`, `open`, `partial_entry`, `partial_close`, `cancelled`, `rejected`, `close`, `triggered`

---

### POST /exchange/v1/margin/orders/create

Places a leveraged margin order with optional bracket levels.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `market` | string | Yes | Trading pair |
| `side` | string | Yes | `buy` or `sell` |
| `order_type` | string | Yes | `market_order`, `limit_order`, `stop_limit`, `take_profit` |
| `total_quantity` | number | Yes | Order quantity |
| `price_per_unit` | number | Limit only | Entry price |
| `stop_price` | number | Stop variants | Stop trigger price |
| `target_price` | number | No | Bracket take-profit exit price |
| `sl_price` | number | No | Bracket stop-loss exit price |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "market": "BTCUSDT",
  "side": "buy",
  "order_type": "limit_order",
  "total_quantity": 0.1,
  "price_per_unit": 44000.00,
  "target_price": 46000.00,
  "sl_price": 43000.00,
  "timestamp": 1524211224000
}
```

**Sample response**
```json
{
  "id": "margin-order-001",
  "market": "BTCUSDT",
  "side": "buy",
  "status": "open",
  "total_quantity": 0.1,
  "price_per_unit": 44000.00,
  "target_price": 46000.00,
  "sl_price": 43000.00,
  "created_at": 1783421549770
}
```

---

### POST /exchange/v1/margin/orders/cancel

Cancels an open margin order before entry is filled.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "margin-order-001", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "message": "success", "code": 200 }
```

---

### POST /exchange/v1/margin/orders/exit

Immediately exits an active margin position at market price.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin position/order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "margin-order-001", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "message": "exit order placed", "code": 200 }
```

---

### POST /exchange/v1/margin/orders/edit_target

Updates the take-profit target price on an open position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin position ID |
| `target_price` | number | Yes | New take-profit price |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "margin-order-001", "target_price": 47000.00, "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "id": "margin-order-001", "target_price": 47000.00, "status": "open" }
```

---

### POST /exchange/v1/margin/orders/edit_sl

Updates the stop-loss price on an open position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin position ID |
| `sl_price` | number | Yes | New stop-loss price |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "margin-order-001", "sl_price": 43500.00, "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "id": "margin-order-001", "sl_price": 43500.00, "status": "open" }
```

---

### POST /exchange/v1/margin/orders/add_margin

Adds collateral to an existing margin position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin position ID |
| `amount` | number | Yes | Amount of collateral to add |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "id": "margin-order-001", "margin": 500.00, "code": 200 }
```

---

### POST /exchange/v1/margin/orders/remove_margin

Withdraws excess collateral from an existing margin position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin position ID |
| `amount` | number | Yes | Amount to remove |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "id": "margin-order-001", "margin": 300.00, "code": 200 }
```

---

### POST /exchange/v1/margin/orders/list

Returns all margin orders/positions for the account.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |
| `page` | integer | No | Page number. Default `1` |
| `size` | integer | No | Records per page. Default/max `200` |

**Sample response**
```json
[
  {
    "id": "margin-order-001",
    "market": "BTCUSDT",
    "side": "buy",
    "status": "open",
    "total_quantity": 0.1,
    "price_per_unit": 44000.00,
    "target_price": 46000.00,
    "sl_price": 43000.00,
    "created_at": 1783421549770
  }
]
```

---

### POST /exchange/v1/margin/orders/status

Returns details for a single margin order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Margin order/position ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{
  "id": "margin-order-001",
  "market": "BTCUSDT",
  "side": "buy",
  "status": "partial_entry",
  "total_quantity": 0.1,
  "filled_quantity": 0.05,
  "price_per_unit": 44000.00,
  "avg_price": 43990.00,
  "target_price": 46000.00,
  "sl_price": 43000.00
}
```

---

## Lend APIs

Authentication required. Enables lending of cryptocurrency holdings in exchange for interest.

**Covers:** creating lending offers at a specified rate and duration, settling active loans, and listing all lending orders.

**Use when:** Generating passive yield on idle holdings by lending them out to margin traders on the platform.

---

### POST /exchange/v1/funding/lend

Creates a new lending order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `currency_short_name` | string | Yes | Asset to lend (e.g. `USDT`) |
| `side` | string | Yes | Always `lend` |
| `amount` | number | Yes | Amount to lend |
| `interest` | number | Yes | Daily interest rate percentage |
| `duration` | integer | Yes | Lending period in days |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "currency_short_name": "USDT",
  "side": "lend",
  "amount": 1000.00,
  "interest": 0.1,
  "duration": 8,
  "timestamp": 1524211224000
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Lending order ID |
| `currency_short_name` | string | Asset lent |
| `amount` | number | Amount lent |
| `interest` | number | Interest rate |
| `duration` | integer | Lending duration in days |
| `status` | string | `active` or `close` |
| `created_at` | number | Creation time in Unix ms |

**Sample response**
```json
{
  "id": "lend-order-abc123",
  "currency_short_name": "USDT",
  "amount": 1000.00,
  "interest": 0.1,
  "duration": 8,
  "status": "active",
  "created_at": 1563975611942
}
```

---

### POST /exchange/v1/funding/settle

Closes an active lending order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Lending order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "id": "lend-order-abc123", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "status": "success", "message": "Order settled", "code": 200 }
```

---

### POST /exchange/v1/funding/fetch_orders

Returns all lending orders for the account.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |
| `page` | integer | No | Page number. Default `1` |
| `size` | integer | No | Records per page. Default/max `200` |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Lending order ID |
| `currency_short_name` | string | Asset |
| `amount` | number | Lent amount |
| `interest` | number | Interest rate |
| `duration` | integer | Duration in days |
| `side` | string | Always `lend` |
| `status` | string | `active` or `close` |
| `created_at` | number | Creation time in Unix ms |
| `settled_at` | number | Settlement time in Unix ms (`null` if still active) |

**Sample response**
```json
[
  {
    "id": "lend-order-abc123",
    "currency_short_name": "USDT",
    "amount": 1000.00,
    "interest": 0.1,
    "duration": 8,
    "side": "lend",
    "status": "close",
    "created_at": 1563975611942,
    "settled_at": 1565615166177
  }
]
```

---

## Futures APIs

Authentication required for private endpoints. Public market data endpoints require no authentication.

**Covers:** placing and cancelling futures orders, tracking positions and unrealized PnL, adjusting leverage, managing margin, setting TP/SL, and querying the futures wallet.

**Use when:** Speculating on price direction with leverage, hedging an existing spot position, or trading contracts without owning the underlying asset.

---

### Futures Market Data (Public)

No authentication required.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/exchange/v1/futures/instruments` | List all active futures contracts |
| `GET` | `/exchange/v1/futures/instruments/{symbol}` | Details for a specific contract |
| `GET` | `/exchange/v1/futures/market_data/trade_history` | Recent trades for a contract |
| `GET` | `/exchange/v1/futures/market_data/orderbook` | Order book for a contract |
| `GET` | `/exchange/v1/futures/market_data/candles` | OHLCV candles for a contract |
| `GET` | `/exchange/v1/futures/prices` | Current mark and last prices |
| `GET` | `/exchange/v1/futures/pair_stats` | 24h stats per contract |

**Common query parameters:** `symbol` (string), `interval` (string), `limit` (integer), `startTime` (integer), `endTime` (integer)

---

### POST /exchange/v1/futures/orders/create

Places a new futures order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Contract identifier (e.g. `BTCUSDT`) |
| `side` | string | Yes | `buy` or `sell` |
| `type` | string | Yes | `market` or `limit` |
| `quantity` | number | Yes | Contract quantity |
| `price` | number | Limit only | Limit price |
| `leverage` | integer | No | Leverage multiplier. Default `1` |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "type": "limit",
  "quantity": 0.01,
  "price": 44000.00,
  "leverage": 5,
  "timestamp": 1524211224000
}
```

**Sample response**
```json
{
  "id": "futures-order-001",
  "symbol": "BTCUSDT",
  "side": "buy",
  "type": "limit",
  "quantity": 0.01,
  "price": 44000.00,
  "leverage": 5,
  "status": "open",
  "created_at": 1783421549770
}
```

---

### POST /exchange/v1/futures/orders/cancel

Cancels an open futures order.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Futures order ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "message": "success", "code": 200 }
```

---

### POST /exchange/v1/futures/orders/cancel_all

Cancels all open futures orders, optionally filtered by symbol.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | No | Cancel orders for this contract only |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "message": "success", "code": 200 }
```

---

### POST /exchange/v1/futures/orders/list

Returns all futures orders for the account.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | No | Filter by contract |
| `status` | string | No | Filter by order status |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
[
  {
    "id": "futures-order-001",
    "symbol": "BTCUSDT",
    "side": "buy",
    "type": "limit",
    "quantity": 0.01,
    "price": 44000.00,
    "leverage": 5,
    "status": "open",
    "created_at": 1783421549770
  }
]
```

---

### POST /exchange/v1/futures/positions/list

Returns all open futures positions.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Position ID |
| `symbol` | string | Contract |
| `side` | string | `buy` (long) or `sell` (short) |
| `quantity` | number | Position size |
| `entry_price` | number | Average entry price |
| `mark_price` | number | Current mark price |
| `leverage` | integer | Active leverage |
| `unrealized_pnl` | number | Unrealised profit/loss |
| `margin` | number | Margin allocated |
| `margin_type` | string | `isolated` or `cross` |

**Sample response**
```json
[
  {
    "id": "position-001",
    "symbol": "BTCUSDT",
    "side": "buy",
    "quantity": 0.01,
    "entry_price": 44000.00,
    "mark_price": 44800.00,
    "leverage": 5,
    "unrealized_pnl": 8.00,
    "margin": 88.00,
    "margin_type": "isolated",
    "created_at": 1783421549770
  }
]
```

---

### POST /exchange/v1/futures/positions/exit

Exits a position at market price.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `position_id` | string | Yes | Position ID |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "message": "exit order placed", "code": 200 }
```

---

### POST /exchange/v1/futures/positions/add_margin

Adds margin to an isolated position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `position_id` | string | Yes | Position ID |
| `amount` | number | Yes | Margin amount to add |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "position_id": "position-001", "margin": 108.00, "code": 200 }
```

---

### POST /exchange/v1/futures/positions/remove_margin

Removes excess margin from an isolated position.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `position_id` | string | Yes | Position ID |
| `amount` | number | Yes | Margin amount to remove |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
{ "position_id": "position-001", "margin": 68.00, "code": 200 }
```

---

### POST /exchange/v1/futures/tpsl/create

Sets or updates take-profit and stop-loss on an open position. At least one of `tp_price` or `sl_price` must be provided.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `position_id` | string | Yes | Position ID |
| `tp_price` | number | Conditional | Take-profit trigger price |
| `sl_price` | number | Conditional | Stop-loss trigger price |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "position_id": "position-001",
  "tp_price": 48000.00,
  "sl_price": 42000.00,
  "timestamp": 1524211224000
}
```

**Sample response**
```json
{ "position_id": "position-001", "tp_price": 48000.00, "sl_price": 42000.00, "code": 200 }
```

---

### POST /exchange/v1/futures/wallet/transfer

Transfers funds between the spot and futures wallets.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `amount` | number | Yes | Transfer amount |
| `direction` | string | Yes | `to_futures` or `from_futures` |
| `currency` | string | No | Asset code. Default `USDT` |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{ "amount": 500.00, "direction": "to_futures", "currency": "USDT", "timestamp": 1524211224000 }
```

**Sample response**
```json
{ "status": "success", "code": 200 }
```

---

### POST /exchange/v1/futures/wallet/details

Returns the futures wallet balance by currency.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample response**
```json
[
  { "currency": "USDT", "balance": 1200.00, "locked_balance": 440.00 }
]
```

---

## Wallet & Transfer APIs

Authentication required. Manages movement of funds between wallets and sub-accounts.

**Covers:** transferring funds between spot and futures wallets, and moving balances across sub-accounts.

**Use when:** Funding a futures position from your spot wallet, rebalancing between accounts, or managing a multi-account setup programmatically.

---

### POST /exchange/v1/wallets/transfer

Transfers funds between the spot and futures wallets.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `source_wallet_type` | string | Yes | `spot` or `futures` |
| `destination_wallet_type` | string | Yes | `spot` or `futures` |
| `currency_short_name` | string | Yes | Asset code (e.g. `USDT`) |
| `amount` | number | Yes | Amount to transfer |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "source_wallet_type": "spot",
  "destination_wallet_type": "futures",
  "currency_short_name": "USDT",
  "amount": 500.00,
  "timestamp": 1524211224000
}
```

**Sample response**
```json
{ "status": "success", "message": 200, "code": 200 }
```

---

### POST /exchange/v1/wallets/sub_account_transfer

Transfers funds between a master account and a sub-account.

**Authentication:** Required

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `from_account_id` | string | Yes | Source account ID |
| `to_account_id` | string | Yes | Destination account ID |
| `currency_short_name` | string | Yes | Asset code |
| `amount` | number | Yes | Amount to transfer |
| `timestamp` | integer | Yes | Current Unix time in ms |

**Sample request body**
```json
{
  "from_account_id": "master-account-id",
  "to_account_id": "sub-account-id-001",
  "currency_short_name": "USDT",
  "amount": 200.00,
  "timestamp": 1524211224000
}
```

**Sample response**
```json
{ "status": "success", "message": 200, "code": 200 }
```

---

## Spot WebSockets

Real-time streaming over a persistent Socket.io connection. Public channels (trades, order book, prices) require no authentication. Private channels (balance, orders, trade updates) require HMAC-SHA256 signing on connect.

**Covers:** live order book, real-time public trades, personal order fill/cancel notifications, and account balance changes.

**Use when:** Building a live trading terminal, executing latency-sensitive strategies that need immediate fill notifications, or keeping a local order book in sync without polling.

**Dependency:** Socket.io v2.4.0 only.
```bash
npm install [email protected]
```

### Connection and Authentication

```javascript
const io = require('socket.io-client');
const crypto = require('crypto');

const apiKey = 'your_api_key';
const apiSecret = 'your_api_secret';
const timeStamp = Date.now();
const signatureData = crypto
  .createHmac('sha256', apiSecret)
  .update(JSON.stringify({ timeStamp }))
  .digest('hex');

const socket = io('wss://stream.coindcx.com', { transports: ['websocket'] });

socket.on('connect', () => {
  socket.emit('join', {
    channelName: 'coindcx',
    authSignature: signatureData,
    apiKey,
    timeStamp
  });
});
```

---

### Spot WebSocket Channels

#### Balance Update

Fires when account balances change (order placed, filled, or cancelled). **Private.**

**Channel:** `balance-update`

```json
{ "currency": "USDT", "balance": 4500.50, "locked_balance": 1700.00 }
```

---

#### Order Update

Fires on order status changes (new, partial fill, fill, cancel). **Private.**

**Channel:** `order-update`

```json
{
  "id": "815052513",
  "status": "filled",
  "market": "BTCUSDT",
  "side": "buy",
  "total_quantity": 0.5,
  "remaining_quantity": 0,
  "avg_price": 44500.00,
  "updated_at": 1783421700000
}
```

---

#### Trade Update

Fires when one of your orders executes. **Private.**

**Channel:** `trade-update`

```json
{
  "trade_id": 252949810,
  "order_id": "815052513",
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": 44500.00,
  "quantity": 0.2,
  "fee_amount": 0.0089,
  "timestamp": 1780415747836
}
```

---

#### New Trade

Streams public trades for a subscribed market. **Public.**

**Channel:** `{pair}@trade` (e.g. `B-BTC_USDT@trade`)

```json
{ "p": 44600.00, "q": 0.015, "s": "BTCUSDT", "T": 1783425000000, "m": false }
```

---

#### Depth Snapshot

Returns the full order book on initial subscribe. **Public.**

**Channel:** `{pair}@depth` (e.g. `B-BTC_USDT@depth`)

```json
{
  "timestamp": 1783425132686,
  "bids": { "44590.00": "0.15", "44585.00": "0.43" },
  "asks": { "44605.00": "0.09", "44610.00": "0.22" }
}
```

---

#### Depth Update

Streams incremental order book changes. **Public.**

**Channel:** `{pair}@depthUpdate`

```json
{
  "timestamp": 1783425140000,
  "bids": { "44592.00": "0.20" },
  "asks": { "44603.00": "0.00" }
}
```
> A quantity of `"0.00"` means the price level has been removed from the book.

---

#### Candlestick

Streams candle updates for a subscribed pair and interval. **Public.**

**Channel:** `{pair}@kline_{interval}` (e.g. `B-BTC_USDT@kline_1m`)

```json
{ "open": 44200.00, "high": 44800.00, "low": 44100.00, "close": 44600.00, "volume": 312.45, "time": 1783422000000 }
```

---

#### Price Change / LTP

Streams last traded price and 24h stats. **Public.**

**Channel:** `{pair}@ticker`

```json
{
  "market": "BTCUSDT",
  "last_price": "44600.00",
  "change_24_hour": "-1.62",
  "high": "45200.00",
  "low": "43800.00",
  "volume": "1240.55",
  "timestamp": 1783425200000
}
```

---

## Futures WebSockets

Uses the same Socket.io v2.4.0 setup as Spot WebSockets. Private channels require authentication.

**Covers:** futures order book, mark/index price feeds, funding rate, personal position and order updates.

**Use when:** Monitoring funding rate movements in real time, tracking position PnL as prices move, or reacting programmatically to futures order fills without REST polling.

---

### Futures WebSocket Channels

#### Position Update

Fires when a position changes (entry fill, PnL update, partial close, liquidation). **Private.**

**Channel:** `futures-position-update`

```json
{
  "id": "position-001",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": 0.01,
  "entry_price": 44000.00,
  "mark_price": 44900.00,
  "unrealized_pnl": 9.00,
  "leverage": 5,
  "margin": 88.00,
  "updated_at": 1783421800000
}
```

---

#### Order Update

Fires on futures order lifecycle events. **Private.**

**Channel:** `futures-order-update`

```json
{
  "id": "futures-order-001",
  "symbol": "BTCUSDT",
  "side": "buy",
  "status": "filled",
  "quantity": 0.01,
  "price": 44000.00,
  "updated_at": 1783421700000
}
```

---

#### Balance Update

Fires when the futures wallet balance changes. **Private.**

**Channel:** `futures-balance-update`

```json
{ "currency": "USDT", "balance": 700.00, "locked_balance": 440.00 }
```

---

#### Orderbook

Streams the futures contract order book. **Public.**

**Channel:** `{symbol}@futures-depth`

```json
{
  "timestamp": 1783425132000,
  "bids": { "44590.00": "3.50", "44585.00": "1.20" },
  "asks": { "44605.00": "2.10", "44610.00": "0.80" }
}
```

---

#### Candlestick

Streams candle updates for a futures contract. **Public.**

**Channel:** `{symbol}@futures-kline_{interval}` (e.g. `BTCUSDT@futures-kline_1m`)

```json
{ "open": 44200.00, "high": 44900.00, "low": 44100.00, "close": 44800.00, "volume": 85.30, "time": 1783422000000 }
```

---

#### New Trade

Streams public futures trades for a contract. **Public.**

**Channel:** `{symbol}@futures-trade`

```json
{ "price": 44800.00, "quantity": 0.005, "side": "sell", "timestamp": 1783425300000 }
```

---

#### LTP / Price Stats

Streams last traded price, mark price, index price, funding rate, and 24h stats. **Public.**

**Channel:** `{symbol}@futures-ticker`

```json
{
  "symbol": "BTCUSDT",
  "last_price": "44800.00",
  "mark_price": "44820.00",
  "index_price": "44810.00",
  "funding_rate": "0.0001",
  "change_24h": "1.35",
  "volume_24h": "2840.10",
  "timestamp": 1783425400000
}
```
