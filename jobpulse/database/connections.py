import psycopg2
import config


def connect_db():
    return psycopg2.connect(**config.database_options())
