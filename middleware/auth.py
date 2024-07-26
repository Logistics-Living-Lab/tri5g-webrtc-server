import base64
import json
import logging
import os

import bcrypt
from aiohttp import web

from config.app_config import AppConfig


class Auth:

    def __init__(self, auth_file):
        self.auth_file = auth_file

    @web.middleware
    async def basic_auth_middleware(self, request, handler):
        auth_header = request.headers.get('Authorization')

        if auth_header is None:
            return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="Login Required"'})

        auth_type, encoded_credentials = auth_header.split(' ', 1)
        if auth_type.lower() != 'basic':
            return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="Login Required"'})

        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        username, password = decoded_credentials.split(':', 1)

        if self.check_credentials(username, password):
            return await handler(request)

        return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="Login Required"'})

    def create_user(self, username: str, password: str):
        users = self.__load_user_from_file()
        existing_user = self.get_user(username)
        if existing_user:
            logging.error(f"User [{username}] already exists.")
            return

        hashed_password = bcrypt.hashpw(bytes(password, 'utf-8'), bcrypt.gensalt())
        users.append({
            'username': username,
            'password': str(hashed_password, "utf-8")
        })

        with open(self.auth_file, 'w') as f:
            f.write(json.dumps(users))

    def update_user(self, username: str, password: str):
        if not self.get_user(username):
            logging.error(f"User [{username}] does not exist.")
            return
        self.delete_user(username)
        self.create_user(username, password)
        logging.info(f"User [{username}] updated.")

    def delete_user(self, username: str):
        users = self.__load_user_from_file()
        existing_user = self.get_user(username)
        if existing_user:
            users.remove(existing_user)

        with open(self.auth_file, 'w') as f:
            f.write(json.dumps(users))
        logging.info(f"User [{username}] deleted.")

    def get_user(self, username: str):
        users = self.__load_user_from_file()
        filtered_users = [user for user in users if user["username"] == username]
        if len(filtered_users) > 0:
            return filtered_users[0]
        else:
            return None

    def __load_user_from_file(self):
        users = list()
        if os.path.exists(self.auth_file):
            with open(self.auth_file, 'r') as f:
                raw = f.read()
                if len(raw) > 0:
                    users = json.loads(raw)
        return users

    def check_credentials(self, username, password):
        user = self.get_user(username)
        if not user:
            logging.error(f"User [{username}] does not exist.")
            return False

        return bcrypt.checkpw(password.encode('utf-8'), user["password"].encode('utf-8'))
