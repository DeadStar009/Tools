import requests
import json
import os
from dotenv import load_dotenv
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dateutil.relativedelta import relativedelta

env_path = Path(__file__).resolve().parent.parent / ".env"
print(env_path)

load_dotenv(dotenv_path=env_path)
apiKey = os.getenv("MONDAY_API_KEY")
apiUrl = "https://api.monday.com/v2"
headers = {"Authorization" : apiKey, "API-Version" : "2023-04"}

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
    items_page_by_column_values (limit: 5, board_id: 2011601454, columns: [{{column_id: "text_mkqspa8", column_values: ["{order_number}"]}}]) {{
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
                if j.get('id') == "color_mkqsw3x7":
                    status = j.get('label', 'Unknown')
                elif j.get('id') == "date_mkqs77y1":
                    value = j.get('value', '{}')
                    try:
                        arrival_date = json.loads(value).get('date', 'Unknown')
                    except Exception as e:
                        arrival_date = 'Unknown'
                elif j.get('id') == "text_mkqspa8":
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
    items_page_by_column_values (limit: 5, board_id: 2025865182, columns: [{{column_id: "text_mkqspa8", column_values: ["{order_number}"]}}]) {{
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
            if j.get('id') == "color_mkqsw3x7":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date_mkqs77y1":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text_mkqspa8":
                order_number_value = j.get('value', '')
            order_view = ""
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, order_view, "Resin", item_id, group_name))
    
    return ans


def get_pressed_details(order_number):
    if not order_number:
        print("Error: Order number cannot be empty")
        return None
        
    query_pressed=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 2025865187, columns: [{{column_id: "text_mkqspa8", column_values: ["{order_number}"]}}]) {{
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
            if j.get('id') == "color_mkqsw3x7":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date_mkqs77y1":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text_mkqspa8":
                order_number_value = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Pressed", item_id, group_name))
    
    return ans



###### EMAIL SEARCH ######

def get_painting_details_from_email(email):
    if not email:
        print("Error: Email cannot be empty")
        return None
        
    query_painting=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 2011601454, columns: [{{column_id: "text_mkqs8f8h", column_values: ["{email}"]}}]) {{
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
                if j.get('id') == "color_mkqsw3x7":
                    status = j.get('label', 'Unknown')
                elif j.get('id') == "date_mkqs77y1":
                    value = j.get('value', '{}')
                    try:
                        arrival_date = json.loads(value).get('date', 'Unknown')
                    except Exception as e:
                        arrival_date = 'Unknown'
                elif j.get('id') == "text_mkqspa8":
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
    items_page_by_column_values (limit: 5, board_id: 2025865182, columns: [{{column_id: "text_mkqs8f8h", column_values: ["{email}"]}}]) {{
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
            if j.get('id') == "color_mkqsw3x7":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date_mkqs77y1":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text_mkqspa8":
                order_number_value = j.get('value', '')
            order_view = ""
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, order_view, "Resin", item_id, group_name))
    
    return ans

def get_pressed_details_from_email(email):
    if not email:
        print("Error: Order number cannot be empty")
        return None
        
    query_pressed=f'''query {{
    items_page_by_column_values (limit: 5, board_id: 2025865187, columns: [{{column_id: "text_mkqs8f8h", column_values: ["{email}"]}}]) {{
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
            if j.get('id') == "color_mkqsw3x7":
                status = j.get('label', 'Unknown')
            elif j.get('id') == "date_mkqs77y1":
                value = j.get('value', '{}')
                try:
                    arrival_date = json.loads(value).get('date', 'Unknown')
                except Exception as e:
                    arrival_date = 'Unknown'
            elif j.get('id') == "text_mkqspa8":
                order_number_value = j.get('value', '')
        
        ans.append(details_monday(name, status, arrival_date, order_number_value, None, "Pressed", item_id, group_name))
    
    return ans

###### MAIN FUNCTION ######
def get_Monday_details_testing(order_number):
    if not order_number:
        print("Error: Cannot search with empty order number")
        return None

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

def get_Monday_details_from_email_testing(email):
    if not email:
        print("Error: Cannot search with empty email")
        return None
        
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

