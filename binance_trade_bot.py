from binance.client import Client
import time
import asyncio
import json

#第一单买入比例
first_order_rate = 0.2
#价格波动多少，就买入卖出
per_step = 0.01
#第一单买入的量，分几单卖出
per_order = 4
TICK_SIZE = None



async def main():
    with open('config.json', 'r') as f:
        config = json.load(f)

    bian_key = config['bian_key']
    bian_secret = config['bian_secret']
    
    client = Client(bian_key, bian_secret, {"timeout": 30})

    # 获取账户的U本位合约信息
    futures_account_info = client.futures_account()

    # 获取可用的USDT数量
    available_usdt = float(futures_account_info.get("availableBalance", 0))

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
    sell_quantity = round((btc_quantity / per_order),4)

    await asyncio.sleep(1)
    #第一单买入完成，挂卖出单
    sell_price = avg_price * (1 + per_step)
    sell_price = round(sell_price,2)
    # print(sell_price,per_step)
    do_sell(client,sell_quantity,sell_price)

    check_order(client)


def fetch_tick_size(client):
    global TICK_SIZE
    # 获取交易对的信息
    exchange_info = client.futures_exchange_info()
    symbols_info = exchange_info['symbols']
    
    # 找到BTCUSDT的tick size
    btc_usdt_info = next((symbol for symbol in symbols_info if symbol['symbol'] == 'BTCUSDT'), None)
    if btc_usdt_info is not None:
        TICK_SIZE = float(next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', btc_usdt_info['filters']))['tickSize'])
        print(f"Tick size for BTCUSDT: {TICK_SIZE}")
    else:
        print("BTCUSDT information not found.")


def check_order(client):
    while True:
        open_orders = get_open_orders(client)
        for order in open_orders:
            order_id = order['orderId']
            status = order['status']
            print(order_id,status)
            if status == 'FILLED':
                print(f"Order {order_id} has been filled.")
                process_order(client,order)
        time.sleep(3)


def process_order(client,order):
    side = order['side']
    price = order['avgPrice']
    quantity = order['executedQty']
    if(side == 'BUY'):
        sell_price = price * (1 + per_step)
        do_sell(client,quantity,sell_price)
    else:
        buy_price = price * (1 - per_step)
        do_buy(client,quantity,buy_price)


def do_sell(client,quantity,price):
    quantity = max(0.002,quantity)
    # if TICK_SIZE is None:
    #     fetch_tick_size(client)
    
    price = round(price,1)
    # # 调整卖出价格，确保是tick size的整数倍
    # adjusted_sell_price = round(price / TICK_SIZE) * TICK_SIZE

    print(quantity,price)
    order = client.futures_create_order(
        symbol='BTCUSDT',
        side='SELL',
        type='LIMIT',
        timeInForce='GTC',  # GTC (Good Till Canceled) 表示订单会一直有效直到被成交或取消
        quantity=quantity,
        price=str(price),  # 价格必须以字符串形式传递

        positionSide='LONG'  # 如果使用双向持仓模式，指定为 'LONG' 表示卖出减少多单仓位
    )
    print('卖出挂单',quantity,price,(quantity * price))

def do_buy(client,quantity,price):
    quantity = max(0.002,quantity)

    # if TICK_SIZE is None:
    #     fetch_tick_size(client)
    # 调整卖出价格，确保是tick size的整数倍
    # adjusted_sell_price = round(price / TICK_SIZE) * TICK_SIZE
    price = round(price,1)
    order = client.futures_create_order(
        symbol='BTCUSDT',
        side='BUY',
        type='LIMIT',
        timeInForce='GTC',  # GTC (Good Till Canceled) 表示订单会一直有效直到被成交或取消
        quantity=quantity,
        price=str(price),  # 价格必须以字符串形式传递
        positionSide='LONG'  # 如果使用双向持仓模式，指定为 'LONG' 表示卖出减少多单仓位
    )
    print('买入挂单',quantity,price,(quantity * price))


# 获取所有未成交订单
def get_open_orders(client):
    return client.futures_get_open_orders(symbol='BTCUSDT')


if __name__ == "__main__":
    asyncio.run(main())