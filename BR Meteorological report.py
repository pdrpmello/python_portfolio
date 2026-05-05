# This codes uses the API from Redemet to give the meteorological conditions of an Airport.

import requests
from datetime import datetime

# API key
api_key = "Z55gk7u2FE8QSSskeb0yONomTCyYU2o5cKjfFO6e"

def meteorological_conditions(aerodrome_icao_code, api_key):
    # Get the current time in the required format (YYYYMMDDHH)
    current_time = datetime.now().strftime("%Y%m%d%H")

    # Redemet's API URL with dynamic date and time
    base_url = f"http://redemet.decea.gov.br//api/consulta_automatica/index.php?local={aerodrome_icao_code}&msg=metar&data_ini={current_time}&data_fim={current_time}"
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()

        # Checking the response content type
        if 'application/json' in response.headers.get('Content-Type'):
            data = response.json()
        else:
            data = response.text

        return data

    except requests.exceptions.HTTPError as http_err:
        return f"HTTP error occurred: {http_err}"
    except Exception as err:
        return f"An error occurred: {err}"

def main():
    # User input
    aerodrome_icao_code = input("Enter the ICAO code of a brazillian aerodrome (e.g., SBGR for Guarulhos): ").upper()

    # Calling the function and displaying the result
    forecast = meteorological_conditions(aerodrome_icao_code, api_key)
    print("Forecast Information:")
    print(forecast)

# Running the main function
if __name__ == "__main__":
    main()