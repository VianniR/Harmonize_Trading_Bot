import math
import requests
import json
import time
import robin_stocks as rs
import sys
from pyotp import *

# 1. Grouping global variables at the top for better organization.
image_api_key = 'sHrqQHwRkcuSOyDRrcs+ZA==lmishsfurvpXVGKU'
tickers = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'COIN', 'AAP', 'AMD', 'NVDA',
           'AMZN', 'ZM', 'INTC', 'TGT', 'WMT', 'META', 'SHOP']
all_sell_ids = []
#add each sell id to this list
sent = []
old_messages = []
currently_holding = []
day_buying_power = None
max_trade_amount = None
purchase_url = None
looking_for = None
ticker = None
strike_price = None
current_gain = None
date = None
option_data = None
open_positions = []
rs_open_positions = None





def extract_number(text: str) -> str:
    return ''.join(char for char in text if char.isdigit() or char in '.-')

def find_first_numeric_string(strings):
    for string in strings:
        if string.isnumeric():
            return string
        elif string[0] == '$' and string[1:].isnumeric():
            return string[1:]
    return None

def extract_percentage(input_str):
    # Find the starting position of the number by locating the '(' and then take until '%'
    start_index = input_str.find('(') + 1
    end_index = input_str.find('%)')

    # If both the '(' and '%' are found, extract the number
    if start_index != 0 and end_index != -1:
        number_str = input_str[start_index:end_index]
        return float(number_str)
    else:
        return None


def ocr_space_url(url, overlay=False, api_key='K83655537588957', language='eng'):
    """ OCR.space API request with remote file.
        Python3.5 - not tested on 2.7
    :param url: Image url.
    :param overlay: Is OCR.space overlay required in your response.
                    Defaults to False.
    :param api_key: OCR.space API key.
                    Defaults to 'helloworld'.
    :param language: Language code to be used in OCR.
                    List of available language codes can be found on https://ocr.space/OCRAPI
                    Defaults to 'en'.
    :return: Result in JSON format.
    """

    payload = {'url': url,
               'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               'isTable': False,
               'OCREngine': 2
               }
    r = requests.post('https://api.ocr.space/parse/image',
                      data=payload,
                      )
    return r.content.decode()

def convert_date_v7(old_date: str) -> str:
    return f"2023-{old_date[:-8]}-{old_date[3:-5]}"


def convert_date_v4(date: str) -> str:
    try:
        old_date = date.split('/')
        month = str(int(old_date[0])).zfill(2)
        day = str(int(old_date[1])).zfill(2)
        return f"2023-{month}-{day}"
    except Exception as e:
        try:
            old_date = date.split('.')
            month = str(int(old_date[0])).zfill(2)
            day = str(int(old_date[1])).zfill(2)
            return f"2023-{month}-{day}"
        except Exception as e:
            pass


def log_in_to_robinhood():
    totp = TOTP("HTWFY3N3KVVC2NWJ")
    token = totp.now()
    global day_buying_power, max_trade_amount, rs_open_positions
    print('running mark 2, version 14')
    rs.login(username="*********", password="*********", mfa_code=token)
    day_buying_power = float(rs.load_account_profile()['buying_power'])
    max_trade_amount = day_buying_power // 10
    rs_open_positions = rs.get_open_option_positions()
    print(f"Today's Buying Power: {day_buying_power}")
    print(f"Max Trading Power: {max_trade_amount}")
    print(f"Current number of positions: {len(rs_open_positions)}")


def wait_till_filled():
    global rs_open_positions
    while len(rs.get_open_option_positions()) == len(rs_open_positions):
        print('not filled yet')
        time.sleep(.5)
    rs_open_positions = rs.get_open_option_positions()


def retrieve_discord_messages(channel_id, headers):
    try:
        response = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages', headers=headers)
        if response:
            messages = json.loads(response.text)
            for msg in messages:
                if msg['id'] not in sent and (msg['author']['username'] in ['djmuggs', 'HarmonyTrades']):
                    print(msg)
                    sent.append(msg['id'])
    except Exception as e:
        print(e)


def retrieve_and_process_purchase_messages(channel_id, headers):
    global looking_for
    global open_positions
    try:
        response = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages', headers=headers)
        if response:
            messages = json.loads(response.text)
            for msg in messages:
                if msg['id'] in sent:
                    continue
                if msg['author']['username'] == 'djmuggs':
                    process_djmuggs_message(msg)
                elif msg['author']['username'] == 'HarmonyTrades' and 'BTO' in msg['content']:
                    process_harmonytrades_message(msg)
                sent.append(msg['id'])
    except Exception as e:
        print(e)


def process_djmuggs_text(input):
    print('trying other')
    data = {'Max Delta': 1.10,
            'Quantity': 1,
            'Trader': 'Muggs'}

    input_split = input.split()
    data['Ticker'] = None
    for word in input_split:
        for ticker in tickers:
            if word.upper() == ticker:
                data['Ticker'] = ticker
    if data['Ticker'] == 'SPY' or data['Ticker'] == 'QQQ':
        data['Expiration'] = '2023-09-01'
    elif data['Ticker'] is not None:
        data['Expiration'] = '2023-09-01'
    else:
        return 'not found'

    if 'call' in input or 'Call' in input:
        data['Type'] = 'call'
    elif 'put' in input or 'Put' in input:
        data['Type'] = 'put'
    else:
        return 'not found'

    #data['Strike'] = find_first_numeric_string(input_split)
    data['Strike'] = None
    for string in input_split:
        if string.isnumeric():
            data['Strike'] = float(string)
        elif string[0] == '$' and string[1:].isnumeric():
            data['Strike'] = float(string[1:])
    if data['Strike'] is None:
        return 'not found'

    try:
        purchase_price = float(
            rs.find_options_by_expiration_and_strike(data['Ticker'], data['Expiration'],
                                                     str(data['Strike']), data['Type'])[0]['ask_price'])
        data['Purchase Price'] = purchase_price
        data['Stop Loss'] = round((data['Purchase Price'] * .85), 2)
        print(purchase_price)
        if (purchase_price * 100) > max_trade_amount:
            data['Quantity'] = 1
        else:
            data['Quantity'] = int(float(max_trade_amount // float(purchase_price * 100)))

        rs.order_buy_option_limit('open', 'debit', data['Purchase Price'],
                                  (data['Ticker']), data['Quantity'], data['Expiration'],
                                  float(data['Strike']), data['Type'], 'gtc')
        print(data)
        wait_till_filled()
        sell_price = round((data['Purchase Price'] * .75), 2)
        sell_order_id = rs.order_sell_option_stop_limit('close', 'credit',
                                                        sell_price,
                                                        (round((data['Purchase Price'] * .77), 2)),
                                                        data['Ticker'], data['Quantity'],
                                                        data['Expiration'],
                                                        float(data['Strike']), data['Type'], 'gtc')['id']
        data['Sell ID'] = sell_order_id
        data['Sell Price'] = sell_price
        print(data)
        open_positions.append(data)

    except:
        print('failed reading')



def process_djmuggs_message(message):
    # ...[original logic for processing djmuggs' messages]...
    try:
        if 'call' in message['content']:
            looking_for = 'call'
        elif 'put' in message['content']:
            looking_for = 'put'
        image = None
        # clearly the old ver
        print(message['attachments'])
        if message['attachments'] != []:
            url = message['attachments'][0]['url']
            response = requests.get(url)
            with open("image.jpg", "wb") as f:
                f.write(response.content)
                f.close()
            api_url = 'https://api.api-ninjas.com/v1/imagetotext'
            image_file_descriptor = open('image.jpg', 'rb')
            files = {'image': image_file_descriptor}
            r = requests.post(api_url, files=files, headers={'X-Api-Key': image_api_key})
            # print(r.json())
            option_data = r.json()
            gain_index = None
            date_index = None
            strike_index = None
            found_percent = False
            for i in range(len(option_data)):
                if '%' in option_data[i]['text']:
                    gain_index = i
                    found_percent = True
                    break
            for i in range(len(option_data)):
                if '2023' in option_data[i]['text']:
                    date_index = i
                    strike_index = i + 1
                    break
            data_dict = {'Ticker': option_data[9]['text'], 'Strike': float(option_data[strike_index]['text'][1:]),
                         'Expiration': convert_date_v7(option_data[date_index]['text']),
                         'Type': looking_for,
                         'Max Delta': 1.10,
                         'Current Gain': None}

            if found_percent:
                data_dict['Current Gain'] = float(extract_number(option_data[gain_index]['text']))

            else:
                try:
                    test_url = json.loads(ocr_space_url(url))
                    input = None
                    lines = test_url['ParsedResults'][0]['TextOverlay']['Lines']
                    for line in lines:
                        if '%' in line['LineText']:
                            input = line['LineText']
                            break
                    data_dict['Current Gain'] = extract_percentage(input)
                    print(data_dict)
                except Exception as e:
                    print(e)

            purchase_price = float(
                rs.find_options_by_expiration_and_strike(data_dict['Ticker'], data_dict['Expiration'],
                                                         str(data_dict['Strike']), data_dict['Type'])[0]['ask_price'])
            #purchase_price = float(message['content'].split()[1])
            data_dict['Purchase Price'] = purchase_price
            data_dict['Trader'] = 'Muggs'
            data_dict['Stop Loss'] = round((data_dict['Purchase Price'] * .85), 2)

            if (purchase_price * 100) > max_trade_amount:
                data_dict['Quantity'] = 1
            else:
                data_dict['Quantity'] = int(float(max_trade_amount // float(purchase_price * 100)))

            if data_dict['Current Gain'] < 10 and data_dict['Current Gain'] > -10:
                try:
                    rs.order_buy_option_limit('open', 'debit', data_dict['Purchase Price'],
                                              (data_dict['Ticker']), data_dict['Quantity'], data_dict['Expiration'],
                                              float(data_dict['Strike']), data_dict['Type'], 'gtc')
                    print(data_dict)
                    wait_till_filled()
                    sell_price = round((data_dict['Purchase Price'] * .75), 2)
                    sell_order_id = rs.order_sell_option_stop_limit('close', 'credit',
                                                                 sell_price,
                                                                 (round((data_dict['Purchase Price'] * .77), 2)),
                                        data_dict['Ticker'], data_dict['Quantity'], data_dict['Expiration'],
                                   float(data_dict['Strike']), data_dict['Type'], 'gtc')['id']
                    data_dict['Sell ID'] = sell_order_id
                    data_dict['Sell Price'] = sell_price
                    print(data_dict)
                    open_positions.append(data_dict)
                except Exception as e:
                    print(e)
            else:
                print('wont buy')
        else:
            print('no image')
            try:
                process_djmuggs_text(message['content'])
            except Exception as e:
                print(e)


    except Exception as e:
        print(e)


def process_harmonytrades_message(message):
    # ...[original logic for processing HarmonyTrades' messages]...
    try:
        input = message['content'].split()
        data_dict = {'Ticker': input[1],
                     'Strike': float(input[2]),
                     'Expiration': convert_date_v4(input[4]),
                     'Type': input[3].lower()[:-1],
                     'Max Delta': 1.10}
        print(data_dict)
        purchase_price = float(
            rs.find_options_by_expiration_and_strike(data_dict['Ticker'], data_dict['Expiration'],
                                                     str(data_dict['Strike']), data_dict['Type'])[0][
                'ask_price'])
        print(purchase_price)
        #purchase_price = float(input[5])
        data_dict['Purchase Price'] = purchase_price
        data_dict['Trader'] = 'Harmony'

        if (purchase_price * 100) > max_trade_amount:
            data_dict['Quantity'] = 1
        else:
            data_dict['Quantity'] = int(float(max_trade_amount // float(purchase_price * 100)))

        try:
            rs.order_buy_option_limit('open', 'debit', data_dict['Purchase Price'],
                                            (data_dict['Ticker']), data_dict['Quantity'], data_dict['Expiration'],
                                            float(data_dict['Strike']), data_dict['Type'], 'gtc')
            wait_till_filled()
            sell_price = round(data_dict['Purchase Price'] * .85, 2)
            sell_order_id = rs.order_sell_option_stop_limit('close', 'credit',
                                                            sell_price,
                                                            (round((data_dict['Purchase Price'] * .87), 2)),
                                                            data_dict['Ticker'], data_dict['Quantity'],
                                                            data_dict['Expiration'],
                                                            float(data_dict['Strike']), data_dict['Type'], 'gtc')['id']
            data_dict['Sell ID'] = sell_order_id
            data_dict['Sell Price'] = sell_price
            print(data_dict)
            open_positions.append(data_dict)
        except Exception as e:
            print(e)
    except Exception as e:
        print(e)


def update_contract(position):
    rs.cancel_option_order(position['Sell ID'])
    time.sleep(1)
    current_stop = position['Max Delta'] - .1
    position['Sell Price'] = position['Purchase Price'] * current_stop
    position['Sell ID'] = rs.order_sell_option_stop_limit('close', 'credit',
                                                                 (round((position['Purchase Price'] * current_stop), 2)),
                                                                 (round((position['Purchase Price'] * current_stop), 2)),
                                        position['Ticker'], position['Quantity'], position['Expiration'],
                                   float(position['Strike']), position['Type'], 'gtc')['id']

def check_and_sell_positions():
    global open_positions
    for position in open_positions:
        price = float(rs.find_options_by_expiration_and_strike(position['Ticker'], position['Expiration'],
                                                str(position['Strike']), position['Type'])[0]['ask_price'])
        percent_delta = price / position['Purchase Price']
        if position['Sell Price'] >= price:
            open_positions.remove(position)
        elif percent_delta > position['Max Delta']:
            position['Max Delta'] = percent_delta
            update_contract(position)


if __name__ == '__main__':
    log_in_to_robinhood()
    headers = {'authorization': 'MzU1ODg1NTM2OTgxOTQyMjcz.Gdpm53._p3STUW-_HXimc6EMJsN5xMQP3wehaEsEDz0so'}
    timeout = time.time() + 3
    while time.time() <= timeout:
        retrieve_discord_messages('719779371849744414', headers)
        retrieve_discord_messages('765030051955605545', headers)

    print('completed 3 seconds')
    while True:
        check_and_sell_positions()
        retrieve_and_process_purchase_messages('719779371849744414', headers)
        retrieve_and_process_purchase_messages('765030051955605545', headers)
        #option_id = rs.order_buy_option_limit('open', 'debit', .01, 'QQQ', 1, '2023-08-23', 370, 'call', 'gtc')['id']
        rs_open_positions = rs.get_open_option_positions() #remove exception for cancel order?
        #time.sleep(5)
        #rs.cancel_option_order(option_id)
        time.sleep(.1)
