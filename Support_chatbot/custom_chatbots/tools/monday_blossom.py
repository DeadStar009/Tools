import requests
import json
import os
from dotenv import load_dotenv
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dateutil.relativedelta import relativedelta
import base64
import io

env_path = Path(__file__).resolve().parent.parent / ".env"
print(env_path)

load_dotenv(dotenv_path=env_path)
apiKey = os.getenv("MONDAY_API_KEY")
apiUrl = "https://api.monday.com/v2"
file_url="https://api.monday.com/v2/file"
headers = {"Authorization" : apiKey, "API-Version" : "2023-04"}
headers2 = {"Authorization" : apiKey, "API-Version" : "2024-04"}
from Support_chatbot.custom_chatbots.tools.monday_testing import get_Monday_details_testing,get_Monday_details_from_email_testing

testing_check=os.getenv("TESTING_CHECK")

class details_monday:
    def __init__(self,name,status,arrival_date,order_number,order_view,order_type,item_ids,group_name=None):
        self.name=name
        self.status=status
        self.arrival_date=arrival_date
        self.order_number=order_number
        self.order_view=order_view
        self.order_type=order_type
        self.item_id=item_ids
        self.group_name=group_name
    
    def get_details(self):
        return self.name,self.status,self.arrival_date,self.order_number,self.order_view,self.order_type,self.group_name
    
    def str_details(self):
        result = f"Name: {self.name}\nStatus: {self.status}"
        
        if self.arrival_date != 'Unknown':
            result += f"\nFlowers Recieved Date: {self.arrival_date}"
            
        result += f"\nOrder Number: {self.order_number}"
        
        if self.order_view is not None and self.order_view:
            result += f"\nOrder View: {self.order_view}"
            
        result += f"\nOrder Type: {self.order_type}"
        
        if self.group_name is not None and self.group_name != 'Unknown':
            result += f"\nCurrent Stage: {self.group_name}"
            
        return result


#### Helper Functions ####

def cutoff_date(date_str):
    # date_str is in the format of "2025-05-16"
    # we need to check if the date is more than 4 months from the current date 
    # If true then order cannot be updated
    given_date = datetime.strptime(date_str, "%Y-%m-%d")
    current_date = datetime.now()
    threshold_date = given_date + relativedelta(months=4)
    if current_date > threshold_date:
        return True
    else:
        return False


###### Details from Order Number ######
def get_painting_details(order_number):
    if not order_number:
        print("Error: Order number cannot be empty")
        return None
        
    query_painting=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 7874400216, columns: [{{column_id: "text_mkkybb4e", column_values: ["{order_number}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_painting}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()  # Raise exception for 4XX/5XX responses
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting painting details for order {order_number}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting painting details: {e}")
        return None

    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for painting order {order_number}")
        return None

    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])

    if not a:
        print(f"No details found in painting for order {order_number}")
        return None

    ans=[]
    for i in range(len(a)):
        try:
            item_id=a[i].get("id")
            name=a[i].get('name', 'Unknown')
            status = 'Unknown'
            arrival_date = 'Unknown'
            order_number_value = ''
            group_name = a[i].get('group', {}).get('title', 'Unknown')
            
            for j in a[i].get('column_values', []):
                if j.get('id') == "status":
                    status = j.get('label', 'Unknown')
                elif j.get('id') == "date4":
                    value = j.get('value', '{}')
                    try:
                        arrival_date = json.loads(value).get('date', 'Unknown')
                    except Exception as e:
                        arrival_date = 'Unknown'
                elif j.get('id') == "text_mkkybb4e":
                    order_number_value = j.get('value', '')
            
            ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Painting", item_id, group_name))
        except Exception as e:
            print(f"Error processing painting item: {e}")
            continue
    
    return ans

def get_resin_details(order_number):
    if not order_number:
        print("Error: Order number cannot be empty")
        return None
        
    query_resin=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 1736814970, columns: [{{column_id: "text2", column_values: ["{order_number}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_resin}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting resin details for order {order_number}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting resin details: {e}")
        return None
        
    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for resin order {order_number}")
        return None
        
    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])
    
    if not a:
        print(f"No details found in resin for order {order_number}")
        return None

    ans=[]
    for i in range(len(a)):
        item_id=a[i].get("id")
        name=a[i].get('name', 'Unknown')
        status = 'Unknown'
        arrival_date = 'Unknown'
        order_number_value = ''
        order_view = ''
        group_name = a[i].get('group', {}).get('title', 'Unknown')
        
        for j in a[i].get('column_values', []):
            if j.get('id') == "status":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date4":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text2":
                order_number_value = j.get('value', '')
            elif j.get('id') == "text28":
                order_view = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, order_view, "Resin", item_id, group_name))
    
    return ans


def get_pressed_details(order_number):
    if not order_number:
        print("Error: Order number cannot be empty")
        return None
        
    query_pressed=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 5511004697, columns: [{{column_id: "text7", column_values: ["{order_number}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_pressed}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting pressed details for order {order_number}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting pressed details: {e}")
        return None
        
    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for pressed order {order_number}")
        return None
        
    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])
    
    if not a:
        print(f"No details found in pressed for order {order_number}")
        return None

    ans=[]
    for i in range(len(a)):
        item_id=a[i].get("id")
        name=a[i].get('name', 'Unknown')
        status = 'Unknown'
        arrival_date = 'Unknown'
        order_number_value = ''
        group_name = a[i].get('group', {}).get('title', 'Unknown')
        
        for j in a[i].get('column_values', []):
            if j.get('id') == "status":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "arrival_date":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text7":
                order_number_value = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Pressed", item_id, group_name))
    
    return ans




###### EMAIL SEARCH ######

def get_painting_details_from_email(email):
    if not email:
        print("Error: Email cannot be empty")
        return None
        
    query_painting=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 7874400216, columns: [{{column_id: "email_mkkytxjj", column_values: ["{email}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_painting}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()  # Raise exception for 4XX/5XX responses
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting painting details for email {email}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting painting details: {e}")
        return None

    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for painting email {email}")
        return None

    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])

    if not a:
        print(f"No details found in painting for email {email}")
        return None

    ans=[]
    for i in range(len(a)):
        try:
            item_id=a[i].get("id")
            name=a[i].get('name', 'Unknown')
            status = 'Unknown'
            arrival_date = 'Unknown'
            order_number_value = ''
            group_name = a[i].get('group', {}).get('title', 'Unknown')
            
            for j in a[i].get('column_values', []):
                if j.get('id') == "status":
                    status = j.get('label', 'Unknown')
                elif j.get('id') == "date4":
                    value = j.get('value', '{}')
                    try:
                        arrival_date = json.loads(value).get('date', 'Unknown')
                    except Exception as e:
                        arrival_date = 'Unknown'
                elif j.get('id') == "text_mkkybb4e":
                    order_number_value = j.get('value', '')
            
            ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Painting", item_id, group_name))
        except Exception as e:
            print(f"Error processing painting item: {e}")
            continue
    
    return ans

def get_resin_details_from_email(email):
    if not email:
        print("Error: Order number cannot be empty")
        return None
        
    query_resin=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 1736814970, columns: [{{column_id: "email", column_values: ["{email}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_resin}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting resin details for email {email}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting resin details: {e}")
        return None
        
    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for resin email {email}")
        return None
        
    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])
    
    if not a:
        print(f"No details found in resin for email {email}")
        return None

    ans=[]
    for i in range(len(a)):
        item_id=a[i].get("id")
        name=a[i].get('name', 'Unknown')
        status = 'Unknown'
        arrival_date = 'Unknown'
        order_number_value = ''
        order_view = ''
        group_name = a[i].get('group', {}).get('title', 'Unknown')
        
        for j in a[i].get('column_values', []):
            if j.get('id') == "status":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date4":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text2":
                order_number_value = j.get('value', '')
            elif j.get('id') == "text28":
                order_view = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, order_view, "Resin", item_id, group_name))
    
    return ans

def get_pressed_details_from_email(email):
    if not email:
        print("Error: Order number cannot be empty")
        return None
        
    query_pressed=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 5511004697, columns: [{{column_id: "email7", column_values: ["{email}"]}}]) {{
        cursor
        items {{
        id
        name
        group {{
            title
        }}
        column_values {{
            id
            type
            value
            ... on StatusValue  {{ 
                label
                update_id
            }}
        }}
        }}
    }}
    }}'''
    data={"query":query_pressed}
    
    try:
        r=requests.post(url=apiUrl, json=data, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout error when getting pressed details for email {email}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error in getting pressed details: {e}")
        return None
        
    try:
        a=r.json()
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Monday API for pressed email {email}")
        return None
        
    a=a.get('data', {}).get('items_page_by_column_values', {}).get('items', [])
    
    if not a:
        print(f"No details found in pressed for email {email}")
        return None

    ans=[]
    for i in range(len(a)):
        item_id=a[i].get("id")
        name=a[i].get('name', 'Unknown')
        status = 'Unknown'
        arrival_date = 'Unknown'
        order_number_value = ''
        group_name = a[i].get('group', {}).get('title', 'Unknown')
        
        for j in a[i].get('column_values', []):
            if j.get('id') == "status":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "arrival_date":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text7":
                order_number_value = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Pressed", item_id, group_name))
    
    return ans



###### MAIN FUNCTION ######
def get_Monday_details(order_number):
    if not order_number:
        print("Error: Cannot search with empty order number")
        return None
    
    if testing_check=="True":
        ans=get_Monday_details_testing(order_number)
        return ans

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit each task to the thread pool
            futures = [
                executor.submit(get_painting_details, order_number),
                executor.submit(get_resin_details, order_number),
                executor.submit(get_pressed_details, order_number)
            ]
            
            correct_details = []
            for future in as_completed(futures):
                try:
                    details = future.result()
                    if details is not None:
                        correct_details.extend(details)
                except Exception as e:
                    print(f"Error retrieving details: {e}")
                    
            if not correct_details:
                print(f"No results found for order number: {order_number}")
                return None
            return correct_details
    except Exception as e:
        print(f"Error retrieving Monday details: {e}")
        return None

def get_Monday_details_from_email(email):
    if not email:
        print("Error: Cannot search with empty email")
        return None
    
    if testing_check=="True":
        ans=get_Monday_details_from_email_testing(email)
        return ans
        
    try:    
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(get_painting_details_from_email, email),
                executor.submit(get_resin_details_from_email, email),
                executor.submit(get_pressed_details_from_email, email)
            ]
        
        correct_details = []
        for future in as_completed(futures):
            try:
                details = future.result()
                if details is not None:
                    correct_details.extend(details)
            except Exception as e:
                print(f"Error retrieving details: {e}")
                
        if not correct_details:
            print(f"No results found for email: {email}")
            return None
        return correct_details
    except Exception as e:
        print(f"Error retrieving Monday details: {e}")
        return None


###### ORDER UPDATE ######
def get_correct_order(order_number,email, name):

    correct_order=[]

    if order_number is not None and name is not None and email is not None:
        ans=get_Monday_details(order_number)
        if ans is not None:
            for i in ans:
                names=str(name).lower().strip()
                order_name=str(i.name).lower().strip()
                print(names)
                print(order_name)
                if names in order_name:
                    correct_order.append(i)

        ans2=get_Monday_details_from_email(email)
        if ans2 is not None:
            for i in ans2:
                for i in ans2:
                    for j in correct_order:
                        if i.item_id!=j.item_id:
                            correct_order.append(i)

        print(correct_order)
    elif order_number is not None and name is not None and email is None:
        ans=get_Monday_details(order_number)
        if ans is not None:
            for i in ans:
                names=str(name).lower().strip()
                order_name=str(i.name).lower().strip()
                print(names)
                print(order_name)
                if names in order_name:
                    correct_order.append(i)

    elif (order_number is  None or name is None )and email is not None:
        ans=get_Monday_details_from_email(email)
        if ans is not None:
            for i in ans:
                correct_order.append(i)
    
    else:
        return None

    if correct_order==[]:
        return None
    return correct_order


def update_in_monday(order_number,name,email,details):
    correct_order=get_correct_order(order_number,email, name)
    if correct_order is not None:
        for i in correct_order:
            if i.arrival_date != 'Unknown':
                if cutoff_date(i.arrival_date):
                    return "Cannot update order as it is more than 4 months old from the date of flowers recieved. We recieved the flowers on "+i.arrival_date+". and the current date is "+datetime.now().strftime("%Y-%m-%d")+"You need to create a new order from the website.",True

            body="By AI BOT from <b>Debales Support Chatbot</b>\n\n" + details

            query4=f'''mutation {{  
            create_update (item_id: {i.item_id}, body: "{body}") {{
                id
            }}
            }}'''
            data = {'query' : query4}

            r=requests.post(url=apiUrl, json=data, headers=headers)
            print(r.json())

            if r.status_code==200:
                return correct_order[0].order_number,False
            else:
                return "Order update failed",True
        
        return correct_order[0].order_number,False
    else:
        return "Order details from (Order number and name) or email not found",True

def update_in_monday_with_screenshot(order_number,name,email,screenshot):
    correct_order=get_correct_order(order_number,email, name)
    if correct_order is not None:
        for i in correct_order:
           
            body="By AI BOT from <b>Debales Support Chatbot</b>"

            query4=f'''mutation {{  
            create_update (item_id: {i.item_id}, body: "{body}") {{
                id
            }}
            }}'''
            data = {'query' : query4}

            r=requests.post(url=apiUrl, json=data, headers=headers)
            print("create_update in monday blossom add screenshot = ",r.json())

            if r.status_code==200:
                update_id=r.json().get("data",{}).get("create_update",{}).get("id",None)
                if update_id is not None:
                    jpeg_bytes = base64.b64decode(screenshot)

                    # Create a file-like object from the bytes
                    jpeg_file = io.BytesIO(jpeg_bytes)

                    # Your payload
                    payload =  {'query': 'mutation ($file: File!) { add_file_to_update (file: $file, update_id: '+update_id+') { id url } }',
                                    'map': '{"image":"variables.file"}'
                                }
                    
                    # Updated files parameter using the base64-decoded data
                    files = [
                        ('image', ('screenshot.jpg', jpeg_file, 'image/jpeg'))
                    ]
                    r2=requests.post(url=file_url, data=payload, headers=headers2, files=files)
                    print("add_file_to_update in monday blossom add screenshot = ",r2.json())
                    if r2.status_code!=200:
                        # image_url=r2.json().get("data",{}).get("add_file_to_update",{}).get("url",None)
                        # print("image_url = ",image_url)
                        # if image_url is not None:
                        #     body='By AI BOT from <b>Debales Support Chatbot</b>\n\n<img src=\"'+image_url+'\" alt=\"screenshot\">'  
                        #     payload2=f'''mutation {{
                        #             edit_update (id: {update_id}, body: "{body}") {{
                        #             id
                        #             }}
                        #             }}'''
                        #     data2 = {'query' : payload2}
                        #     r3=requests.post(url=apiUrl, json=data2, headers=headers)

                        #     print(r3.json())
                        #     if r3.status_code==200:
                        #         return True
                        #     else:
                        #         return False

                        return False
                    
                else:
                    return False
                
            else:
                return False
    else:
        return False
    
    return True
