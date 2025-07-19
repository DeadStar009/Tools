import requests
import json
import os
import json
import requests
from datetime import datetime

API_VERSION   = "2024-04"        # or "unstable" if you truly need it
shopify_api_key=os.environ.get("BLOSSOM_SHOPIFY_API_KEY")
SHOP_DOMAIN=os.environ.get("BLOSSOM_SHOPIFY_SHOP_DOMAIN")

from Database.mongo_db.mongo import MongoDatabase
mongo_db=MongoDatabase()

def execute_query(graphql_query):
    try:
        payload = {"query": graphql_query}
        url = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": shopify_api_key,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()               
        data = response.json()
        return data
    except Exception as e:
        print(f"\n\nError executing GraphQL query: {str(e)}\n\n")
        raise


def get_order_details(order_number,chat_id,bot_id,session_id):
    try:
        order_number=str(order_number).replace('"','').replace("'","").replace(" ","")
        if order_number is None:
            return "\n\nOrder id is not found\n\n"
        elif order_number[0]!='#':
            order_number=f"#{order_number}"
        graphql_query = f"""
        query {{
          orders(first: 50, query: "name:{order_number}") {{
            edges {{
              node {{
                id
                name
                currentTotalPriceSet {{
                  shopMoney {{
                    amount
                    currencyCode
                  }}
                }}
                lineItems(first: 50) {{
                  nodes {{
                    id
                    name
                    variantTitle
                    variant {{
                      id
                    }}
                    quantity
                    originalTotalSet {{
                      shopMoney {{
                        amount
                      }}
                    }}
                    discountedTotalSet {{
                      shopMoney {{
                        amount
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = execute_query(graphql_query)
        print("In get_order_details data: ", data)

        products = []
        total_price = 0

        for edge in data['data']['orders']['edges']:
            order_node = edge['node']
            total_price = float(order_node['currentTotalPriceSet']['shopMoney']['amount'])
            for item in order_node['lineItems']['nodes']:
                price = float(item['originalTotalSet']['shopMoney']['amount'])
                price_after_discount = float(item['discountedTotalSet']['shopMoney']['amount'])
                products.append({
                    "id": item['id'],
                    "title": item['name'],
                    "Variant_id": item['variant']['id'] if item['variant'] else None,
                    "Variant_title": item['variantTitle'],
                    "price": price,
                    "discount": round(price - price_after_discount, 2),
                    "discount_percentage": str(round((price - price_after_discount) / price * 100, 2))+"%",
                    "price_after_discount": price_after_discount
                })

        order_update_dict={
            "order_number": order_number,
            "chat_id": chat_id,
            "bot_id": bot_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "Products": products,
            "Total_price": total_price
        }
        mongo_db.logging_order_update(order_update_dict)
        return True

    except Exception as e:
        print(f"\n\nError getting order details: {str(e)}\n\n")
        return False

###### FIND ORDER ID ######
def get_order_id(order_number):
    try:
        order_id=None
        graphql_query = f"""
        query {{
        orders(first: 10, query: "name:{order_number}") {{
            edges {{
            cursor
            node {{
                id
                name
                lineItems(first: 10) {{
                nodes {{
                    id
                    name
                    variantTitle
                    variant {{
                    id
                    }}
                    quantity
                    discountedTotalSet {{
                    shopMoney {{ amount currencyCode }}
                    }}
                }}
                }}
                }}
            }}
            }}
            
        }}
        """
        data=execute_query(graphql_query)
        print("In get_order_id data: ",data)
        for edge in data['data']['orders']['edges']:
            order_id=edge['node']['id']
        return order_id
    except Exception as e:
        print(f"\n\nError getting order ID: {str(e)}\n\n")
        raise


def get_order_edit_begin_id(order_id):
    try:
        graphql_query = f"""
        mutation orderEditBegin {{
        orderEditBegin(id: "{order_id}") {{
            calculatedOrder {{
            id
            }}
        }}
        }}
        """
        data=execute_query(graphql_query)
        print("In get_order_edit_begin_id data: ",data)

        return data['data']['orderEditBegin']['calculatedOrder']['id']
    except Exception as e:
        print(f"\n\nError getting order edit begin ID: {str(e)}\n\n")
        raise


def add_line_item_and_discount(order_edit_id, variant_id, quantity=1, discount_pct=15):
    """
    1. Adds a ProductVariant line item to an order edit.
    2. Applies a percentage discount to that line item.
    Returns the same order_edit_id on success.
    Raises on any API error (raises exception with details).
    """
    try:
        print(f"\n\norder_edit_id: {order_edit_id}\n\nvariant_id: {variant_id}\n\nquantity: {quantity}\n\ndiscount_pct: {discount_pct}\n\n")
        # 1. Add the variant to the order edit
        variant_gid = f"gid://shopify/ProductVariant/{variant_id}"  # Global ID format :contentReference[oaicite:0]{index=0}
        add_variant_mutation = f"""
        mutation addVariantToEdit {{
          orderEditAddVariant(
            id: "{order_edit_id}"
            variantId: "{variant_gid}"
            quantity: {quantity}
            allowDuplicates: true
          ) {{
            calculatedLineItem {{ id title quantity }}
            calculatedOrder {{ subtotalPriceSet {{ presentmentMoney {{ amount currencyCode }} }} }}
            userErrors {{ field message }}
          }}
        }}
        """
        result = execute_query(add_variant_mutation)
        line_item = result['data']['orderEditAddVariant']['calculatedLineItem']
        line_item_id = line_item['id']

        # 2. Apply the percentage discount to that line item
        #    Using OrderEditAppliedDiscountInput (description, percentValue) :contentReference[oaicite:1]{index=1}
        discount_mutation = f"""
        mutation addLineItemDiscount {{
          orderEditAddLineItemDiscount(
            id: "{order_edit_id}"
            lineItemId: "{line_item_id}"
            discount: {{
              description: "{int(discount_pct)}% off"
              percentValue: {discount_pct}
            }}
          ) {{
            addedDiscountStagedChange {{ 
              description 
              value {{ ... on PricingPercentageValue {{ percentage }} }} 
            }}
            calculatedLineItem {{
              id
              title
              quantity
              hasStagedLineItemDiscount
            }}
            calculatedOrder {{
              subtotalPriceSet {{ presentmentMoney {{ amount currencyCode }} }}
              totalPriceSet    {{ presentmentMoney {{ amount currencyCode }} }}
            }}
            userErrors {{ field message }}
          }}
        }}
        """
        if discount_pct != 0:
          discount_result = execute_query(discount_mutation)
          print(f"\n\ndiscount_result: {discount_result}\n\n")
          actual_discount = discount_result['data']['orderEditAddLineItemDiscount']['addedDiscountStagedChange']
          actual_percentage = actual_discount['value']['percentage']
          actual_description = actual_discount['description']
        else:
          actual_percentage = 0.0
          actual_description = ""
        return order_edit_id,actual_percentage,actual_description

    except Exception as e:
        print(f"Error in add_line_item_and_discount: {e}")
        raise


def commit_order_edit(order_edit_id):
    try:
        graphql_query = f"""
        mutation commitOrderEditAndSendInvoice {{
        orderEditCommit(
            id: "{order_edit_id}"   # calculatedOrder.id from orderEditBegin
            notifyCustomer: true                            # emails updated invoice
            staffNote: "Adjusted variant via API"           # optional internal note
        ) {{
            order {{                                        # ✅ edited order, not orderEdit
            id
            name
            subtotalPriceSet {{ presentmentMoney {{ amount currencyCode }} }}
            totalPriceSet   {{ presentmentMoney {{ amount currencyCode }} }}
            }}
            userErrors {{
            field
            message
            }}
        }}
        }}

        """
        data=execute_query(graphql_query)
        print(f"\n\ndata: {data}\n\n")
        return "done"
    except Exception as e:
        print(f"\n\nError committing order edit: {str(e)}\n\n")
        raise


def add_line_item_and_commit(order_number,variantid,quantity=1):
    try:
        order_number=str(order_number).replace('"','').replace("'","").replace(" ","")
        if order_number is None:
            return "\n\nOrder id is not found\n\n"
        elif order_number[0]!='#':
            order_number=f"#{order_number}"

        print(f"\n\norder_number: {order_number}\n\n")
        order_id=get_order_id(order_number)
        print(f"\n\norder_id: {order_id}\n\n")
        order_edit_id=get_order_edit_begin_id(order_id)
        if str(variantid) == "43070878941363" or str(variantid) == "46489435898104":
            discount_pct=0
        else:
            discount_pct=15
        order_edit_id, discount_percentage, discount_description = add_line_item_and_discount(order_edit_id,variantid,quantity,discount_pct)
        commit_order_edit(order_edit_id)
        return {
            "message": "\n\nProduct has been added to the order and the new bill has been sent to the customer email. Please pay the amount from the email.\n\n",
            "discount_percentage": discount_percentage,
            "discount_description": discount_description
        }
    except Exception as e:
        print(f"\n\nError in add_line_item_and_commit: {str(e)}\n\n")
        return "\n\nFailed to add product to order. Please try again later.\n\n"
        

