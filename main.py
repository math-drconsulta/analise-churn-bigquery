from google.cloud import bigquery

client = bigquery.Client(project="airflow-datalake-prod")

# Testa listando os datasets do projeto
datasets = list(client.list_datasets())

if datasets:
    for ds in datasets:
        print(ds.dataset_id)
else:
    print("Nenhum dataset encontrado (mas a conexão funcionou!)")
