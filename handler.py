import json
import boto3

# Dados mockados
erp_data = [
    {
        "id": 10001,
        "valor": 152.00,
        "data": "10/01/2024",
        "frete": 5.90,
        "desconto": "5%",
        "status": "finished"
    },
    {
        "id": 10002,
        "valor": 250.00,
        "data": "10/01/2024",
        "frete": 5.90,
        "desconto": "R$50,00",
        "status": "finished"
    },
    {
        "id": 10003,
        "valor": 145.50,
        "data": "11/01/2024",
        "frete": 5.90,
        "desconto": "3%",
        "status": "finished"
    },
    {
        "id": 10004,
        "valor": 120.00,
        "data": "11/01/2024",
        "frete": 5.90,
        "desconto": None,
        "status": "finished"
    },
    {
        "id": 10005,
        "valor": 50.00,
        "data": "11/01/2024",
        "frete": 5.90,
        "desconto": None,
        "status": "finished"
    },
    {
        "id": 10006,
        "valor": 35.00,
        "data": "12/01/2024",
        "frete": 0.00,
        "desconto": None,
        "status": "finished"
    },
    {
        "id": 10007,
        "valor": 35.00,
        "data": "12/01/2024",
        "frete": 0.00,
        "desconto": None,
        "status": "finished"
    },
    {
        "id": 10008,
        "valor": 180.00,
        "data": "12/01/2024",
        "frete": 5.90,
        "desconto": "10%",
        "status": "in progress"
    },
    {
        "id": 10009,
        "valor": 9.90,
        "data": "12/01/2024",
        "frete": 5.90,
        "desconto": None,
        "status": "in progress"
    }
]

def lambda_handler(event, context):
    # Tratar e transformar os dados
    transformed_data = transform_data(erp_data)
    
    # Salvar os dados transformados em um bucket S3
    s3 = boto3.client('s3')
    bucket_name = 'challenge-bucket737'
    s3.put_object(Bucket=bucket_name, Key='transformed_data.json', Body=json.dumps(transformed_data))
    
    return {
        'statusCode': 200,
        'body': json.dumps('Dados transformados e salvos com sucesso!')
    }

def transform_data(data):
    # Exemplo de transformação: simplificar a estrutura dos dados
    transformed = []
    for entry in data:
        transformed_entry = {
            "id": entry["id"],
            "valor": entry["valor"],
            "data": entry["data"],
            "frete": entry["frete"],
            "desconto": entry["desconto"] if entry["desconto"] else "Nenhum desconto",
            "status": entry["status"]
        }
        transformed.append(transformed_entry)
    return transformed