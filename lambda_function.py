import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import date, datetime
from decimal import Decimal
import email
import json
import re
import requests

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


s3_client = boto3.client('s3')
ddb = boto3.resource('dynamodb', region_name='us-east-1')

EXPENSIFY_URL = "https://integrations.expensify.com/Integration-Server/ExpensifyIntegrations"

MARKET_FUNCTIONS = {
	'uberseat': {
		'pdate': lambda x: datetime.strptime(x.split('Purchase date ')[1], '%B %d, %Y').date() if len(x.split('Purchase date ')) == 2 else None, # Purchase date January 31, 2016
		'amount': lambda x: Decimal(x.replace('$','').split('*')[3]) if len(x.split('*')) == 5 and x.split('*')[1] == 'Total cost' else None # *Total cost* *$36.00*
	},
	'ticketnetwork': {
		'pdate': lambda x: datetime.strptime(x.split(' Order Date: ')[1], '%m/%d/%Y').date() if len(x.split(' Order Date: ')) == 2 else None, # Order Number 18634227 Order Date: 9/30/2015
		'amount': lambda x: Decimal(x.replace('$','').split('*')[3]) if len(x.split('*')) == 5 and x.split('*')[1] == 'Order Total:' else None # *Order Total:* *$114.30*
	},
	'fanxchange': {
		'pdate': lambda x: datetime.strptime(x.split('Purchase date ')[1], '%B %d, %Y').date() if len(x.split('Purchase date ')) == 2 else None, # Purchase date January 31, 2016
		'amount': lambda x: Decimal(x.replace('$','').split('*')[3]) if len(x.split('*')) == 5 and x.split('*')[1] == 'Total cost' else None # *Total cost* *$36.00*
	},
	'razorgator': {
		'pdate': lambda x: datetime.strptime(x.split('*')[1], '%m/%d/%Y').date() if len(x.split('*')) == 5 else None, # *10/22/2015* *2. Order Confirmed *
		'amount': lambda x: Decimal(x.replace('$', '').split(' ')[2]) if len(x.split(' ')) == 4 and x[:12] == 'Order Total ' else None # Order Total $148.95 USD
	},
	'seatgeek': {
		'pdate': lambda x: datetime.strptime(x.split('Date: ')[1], '%a, %b %d, %Y at %I:%M %p').date() if len(x.split('Date: ')) == 2 else None, # Date: Mon, Feb 8, 2016 at 5:38 PM
		'amount': lambda x: Decimal(x.split('Total cost $')[1]) if len(x.split('Total cost $')) == 2 else None # Total cost $9.00
	},
	'telecharge': {
		'pdate': lambda x: datetime.strptime(x.split('Order Date: ')[1], '%m/%d/%Y').date() if len(x.split('Order Date: ')) == 2 else None, # Order Date: 08/30/2015
		'amount': lambda x: Decimal(x.split('Total $')[1]) if len(x.split('Total $')) == 2 else None # Total $319.75
	}
}


def email_handler(event, context):
    
    m = event["Records"][0]["ses"]["mail"]
    bucket = 'seatgeek-expensify'
    key = m["messageId"]
    subject = m["commonHeaders"]["subject"]
    
    sender = m["commonHeaders"]["from"][0]
    email_addr = re.search(r'[\w\.-]+@[\w\.-]+', sender).group(0)
    user_id = get_user_id_from_email(email_addr)
    
    download_path = '/tmp/{}'.format(key)
    
    s3_client.download_file(bucket, key, download_path)
    
    with open(download_path, 'r') as f:
        e = email.message_from_file(f)
    
    body = get_plaintext(e.get_payload())
    lines = body.replace('\r', '').split('\n')
    
    amount, receipt_date = get_amount_date(subject, lines)
    
    response = submit_expense(user_id, receipt_date, amount)
    print response
    
    
def get_amount_date(subject, lines):
    market = get_market(subject, lines)
    amt_fxn = MARKET_FUNCTIONS[market]['amount']
    date_fxn = MARKET_FUNCTIONS[market]['pdate']
    
    amount, receipt_date = None, None
    
    for line in lines:
        if not amount:
            amount = amt_fxn(line)
        if not receipt_date:
            receipt_date = date_fxn(line)
        if amount and receipt_date:
            break
    
    return amount, receipt_date


def get_user_id_from_email(address):
    table = ddb.Table('autoexpensify_email')
    response = table.query(KeyConditionExpression=Key('email').eq(address))
    if response['Items']:
        return response['Items'][-1].get('user_id')
    return None


def get_expensify_credentials(uid):
    
    sg_email, ex_uid, ex_usec = None, None, None
    
    table = ddb.Table('autoexpensify_email')
    response  = table.scan(FilterExpression=Attr('user_id').eq(uid) & Attr('is_sg').eq(True))
    if response['Items']:
        sg_email = response['Items'][-1].get('email')
    
    table = ddb.Table('autoexpensify_user')
    response = table.query(KeyConditionExpression=Key('user_id').eq(uid))
    if response['Items']:
        j = response['Items'][-1]
        ex_uid = j['expensify_partner_user_id']
        ex_usec = j['expensify_partner_user_secret']
            
    if sg_email and ex_uid and ex_usec:
        return (sg_email, ex_uid, ex_usec)
    return None


def get_market(subject, lines):
    for line in lines:
        if line.find('hi@seatgeek.com') >= 0 and subject.find('Telecharge.com') >= 0:
            return 'telecharge'
        if line.find('customerservice@ticketnetwork.com') >= 0 and subject.find('TicketNetwork.com') >= 0:
            return 'ticketnetwork'
        if line.find('rg-support@razorgator.com') >= 0 and subject.find('Order #') >= 0:
            return 'razorgator'
        if line.find('support@fanxchange.com') >= 0 and subject.find('we have received your order') >= 0:
            return 'fanxchange'
        if line.find('help@uberseat.com') >= 0 and subject.find('Your ticket order has been confirmed!') >= 0:
            return 'uberseat'
        if line.find('transactions@seatgeek.com') >= 0 and subject.find('Your ticket') >= 0:
            return 'seatgeek'
    return None


def get_plaintext(body):
    if isinstance(body, list):
        for item in body:
            if item.get_content_type() == 'text/plain':
                return item.get_payload()
            if item.get_content_type() == 'multipart/alternative':
                subbody = item.get_payload()
                for subitem in subbody:
                    if subitem.get_content_type() == 'text/plain':
                        return subitem.get_payload()
    else:
        return body


def used_ticket_perk(uid, yearmo):
    table = ddb.Table('autoexpensify_expense')
    response  = table.scan(FilterExpression=Key('user_id').eq(uid) & Attr('yearmo').eq(yearmo))
    if response['Items']:
        return(sum(response['Items'][0].get('expenses')))
    return 0

        
def submit_expense(uid, receipt_date, amount):
    emp_email, eid, esec = get_expensify_credentials(uid)
    
    yearmo = receipt_date.strftime('%Y%m')
    expensable_amount = int(max(Decimal(120.) - used_ticket_perk(uid, yearmo) - amount, 0)*100)
    
    params = {
        "requestJobDescription": json.dumps({
            "type": "create",
            "credentials": {
                "partnerUserID": eid,
                "partnerUserSecret": esec
            },
            "inputSettings":{
                "type": "expenses",
                "employeeEmail": emp_email,
                "transactionList": [
                    {
                        "created": receipt_date.isoformat(),
                        "currency": "USD",
                        "merchant": "SeatGeek",
                        "amount": expensable_amount,
                        # "externalID": 123456,
                        "comment": "Monthly Ticket Perk {}".format(receipt_date.isoformat()[:7])
                    }
                ]
            }
        })
    }
    print params
    response = requests.get(EXPENSIFY_URL, params = params)
    return response.content
