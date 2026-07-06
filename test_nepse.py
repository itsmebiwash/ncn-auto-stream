import requests
try:
    r = requests.get('https://www.nepalipaisa.com/api/GetIndex')
    print(r.text)
except:
    pass
