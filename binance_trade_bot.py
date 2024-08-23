from binance.client import Client
import time
import asyncio
import json

single_order_usdt = None
open_orders = []
per_step = None
client = None
bian_key = None
bian_secret = None


def init_clinet():
    global client
    client = Client(bian_key, bian_secret, {"timeout": 30})

async def main():
    with open('config.json', 'r') as f:
        config = json.load(f)

    global bian_key
    global bian_secret
    bian_key = config['bian_key']
    bian_secret = config['bian_secret']
    first_order_rate = config['first_order_rate']
    global per_step
    per_step = config['per_step']

    single_order = config['single_order']
    
    init_clinet()

    #当前有开着单，直接监听，不执行挂单
    if(check_position('BTCUSDT')):
        cur_orders = get_open_orders()
        global open_orders
        open_orders = [order['orderId'] for order in cur_orders]  # 提取所有订单的 'orderId'
        check_order()
        return

    # 获取账户的U本位合约信息
    futures_account_info = client.futures_account()

    # 获取可用的USDT数量
    available_usdt = float(futures_account_info.get("availableBalance", 0))

    global single_order_usdt
    single_order_usdt = available_usdt * single_order

    # 第一单的比例
    usdt_to_use = available_usdt * first_order_rate

    # 获取当前BTC的市场价格
    btc_price = float(client.futures_symbol_ticker(symbol="BTCUSDT")['price'])
    print('btc price',btc_price)

    # 检查当前持仓模式
    position_mode = client.futures_get_position_mode()['dualSidePosition']
    # 根据持仓模式设定 positionSide
    if position_mode:
        # 双向持仓模式
        position_side = 'LONG'
    else:
        # 单向持仓模式
        position_side = 'BOTH'


    # 计算购买的BTC数量（20倍杠杆）
    leverage = 20
    btc_quantity = usdt_to_use * leverage / btc_price
    btc_quantity = round(btc_quantity, 3)
    btc_quantity = max(0.002,btc_quantity)

    print('买入BTC数量',btc_quantity)
    # return;
    # 下单买入BTC
    order = client.futures_create_order(
        symbol='BTCUSDT',
        side='BUY',
        type='MARKET',
        quantity=btc_quantity,
        positionSide=position_side
    )

    print(order)
    avg_price = btc_price
    sell_quantity = round((single_order_usdt * leverage / avg_price),3)
    sell_quantity = max(0.002,sell_quantity)

    await asyncio.sleep(3)
    #第一单买入完成，挂卖出单1，价格*101%
    sell_price = avg_price * (1 + per_step)
    reduce_quantity = do_sell(sell_quantity,sell_price)

    remain_quantity = btc_quantity - reduce_quantity

    if(remain_quantity > 0):
        await asyncio.sleep(3)
        #挂卖出单2，价格*102%
        sell_price = avg_price * (1 + per_step * 2)
        reduce_quantity = do_sell(sell_quantity,sell_price)
        remain_quantity -= reduce_quantity

    if(remain_quantity > 0):
        await asyncio.sleep(3)
        #挂卖出单3，价格*103%
        sell_price = avg_price * (1 + per_step * 3)
        do_sell(sell_quantity,sell_price)


    remain_usdt = available_usdt * leverage - (btc_quantity * avg_price)
    buy_quantity = sell_quantity
    
    #挂买入1，价格*99%
    buy_price = avg_price * (1 - per_step)
    if(remain_usdt >= buy_price * buy_quantity):
        await asyncio.sleep(3)
        do_buy(buy_quantity,buy_price)

    
    remain_usdt -= buy_quantity * buy_price
    if(remain_usdt >=  buy_price * buy_quantity):
        await asyncio.sleep(3)
        #挂买入2，价格*98%
        buy_price = avg_price * (1 - per_step * 2)
        do_buy(buy_quantity,buy_price)

    check_order()


# 获取当前持仓信息
def get_current_position(symbol):
    positions = client.futures_account()['positions']
    for position in positions:
        if position['symbol'] == symbol:
            return float(position['positionAmt'])
    return 0.0


# def fetch_tick_size():
#     global TICK_SIZE
#     # 获取交易对的信息
#     exchange_info = client.futures_exchange_info()
#     symbols_info = exchange_info['symbols']
    
#     # 找到BTCUSDT的tick size
#     btc_usdt_info = next((symbol for symbol in symbols_info if symbol['symbol'] == 'BTCUSDT'), None)
#     if btc_usdt_info is not None:
#         TICK_SIZE = float(next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', btc_usdt_info['filters']))['tickSize'])
#         print(f"Tick size for BTCUSDT: {TICK_SIZE}")
#     else:
#         print("BTCUSDT information not found.")

def safe_sell_quantity(quantity):
    # quantity = max(0.002,quantity)
    current_position = get_current_position('BTCUSDT')
    if(current_position < 0.002):
        return current_position
    
    #这单卖完 下一单不足0.002，凑在这单一起卖了
    if(current_position - quantity < 0.002):
        return current_position
    
    quantity = max(0.002,quantity)
    quantity = min(quantity,current_position)
    return quantity;


def check_order():
    while True:
        order_ids = open_orders;
        for order_id in order_ids:
            try:
                order = client.futures_get_order(orderId=order_id, symbol='BTCUSDT')
                status = order.get('status')
                print(order_id,status)
                if status == 'FILLED':
                    print(f"Order {order_id} has been filled.")
                    process_order(order)
                    open_orders.remove(order_id)
                if status == 'EXPIRED':
                    print(f"Order {order_id} is expired.")
                    open_orders.remove(order_id)
            except Exception as e:
                print('check order error',e)
                init_clinet()
                print('init client')

            time.sleep(8)
        time.sleep(8)


def process_order(order):
    side = order['side']
    price = float(order['avgPrice'])
    quantity = float(order['executedQty'])
    if(side == 'BUY'):
        sell_price = price * (1 + per_step)
        do_sell(quantity,sell_price)
    else:
        buy_price = price * (1 - per_step)
        do_buy(quantity,buy_price)


def do_sell(quantity,price):
    # quantity = max(0.002,quantity)
    price = round(price,1)
    quantity = safe_sell_quantity(quantity)
    
    if(quantity <= 0):
        print('当前持仓已经全部挂单卖出')
        return;
    try:
        order = client.futures_create_order(
            symbol='BTCUSDT',
            side='SELL',
            type='LIMIT',
            timeInForce='GTC',  # GTC (Good Till Canceled) 表示订单会一直有效直到被成交或取消
            quantity=quantity,
            price=str(price),  # 价格必须以字符串形式传递

            positionSide='LONG'  # 如果使用双向持仓模式，指定为 'LONG' 表示卖出减少多单仓位
        )
        open_orders.append(order['orderId'])
        print('卖出挂单',quantity,price,(quantity * price))
    except Exception as e:
        print('卖出报错',e)
    return quantity

def do_buy(quantity,price):
    quantity = max(0.002,quantity)

    # if TICK_SIZE is None:
    #     fetch_tick_size()
    # 调整卖出价格，确保是tick size的整数倍
    # adjusted_sell_price = round(price / TICK_SIZE) * TICK_SIZE
    price = round(price,1)
    try:
        order = client.futures_create_order(
            symbol='BTCUSDT',
            side='BUY',
            type='LIMIT',
            timeInForce='GTC',  # GTC (Good Till Canceled) 表示订单会一直有效直到被成交或取消
            quantity=quantity,
            price=str(price),  # 价格必须以字符串形式传递
            positionSide='LONG'  # 如果使用双向持仓模式，指定为 'LONG' 表示卖出减少多单仓位
        )
        open_orders.append(order['orderId'])
        print('买入挂单',quantity,price,(quantity * price))
    except Exception as e:
        print('买入报错',e)
    return quantity;


# 获取所有未成交订单
def get_open_orders():
    return client.futures_get_open_orders(symbol='BTCUSDT')


def check_position(symbol):
    # 获取所有合约交易对的仓位信息
    positions = client.futures_position_information()
    
    # 遍历所有仓位，找到对应的symbol
    for position in positions:
        if position['symbol'] == symbol:
            position_amt = float(position['positionAmt'])
            if position_amt != 0:
                print(f"Currently holding {position_amt} units of {symbol}.")
                return True
            else:
                print(f"No open positions for {symbol}.")
                return False

    print(f"No data found for {symbol}.")
    return False

if __name__ == "__main__":
    asyncio.run(main())