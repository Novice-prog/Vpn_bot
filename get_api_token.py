from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv('TOKEN_bot')

Yoo_Api_id = os.getenv('Yoo_Api_id_env')
Yoo_Api_key = os.getenv('Yoo_Api_key_env')

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN_env')

Auth_name = os.getenv('Auth_name_env')
Auth_password = os.getenv('Auth_password_env')
Marzban_url = os.getenv('Marzban_url_env')


from marzban_api_client import Client
from marzban_api_client.api.admin import admin_token
from marzban_api_client.models.body_admin_token_api_admin_token_post import (
     BodyAdminTokenApiAdminTokenPost,
)
from marzban_api_client.models.token import Token
from marzban_api_client.types import Response

login_data = BodyAdminTokenApiAdminTokenPost(
     username= Auth_name,
     password= Auth_password,
 )

client = Client(base_url=Marzban_url)

with client as client:
     token: Token = admin_token.sync(
         client=client,
         body=login_data,
     )
     Marzban_Api_Token = token.access_token
