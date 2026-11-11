import os

# Las pruebas nunca tocan la base real: se fijan antes de importar config (load_dotenv no pisa variables ya definidas)
os.environ["DB_MOTOR"] = "sqlite"
os.environ["DB_ENV"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["AUTH_MODO"] = "demo"
os.environ["ALMACENAMIENTO"] = "local"
os.environ["ENTORNO"] = "desarrollo"
os.environ["APP_ID"] = "16"
os.environ["LOGIN_LOCAL_SIN_APP"] = ""
