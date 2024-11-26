import os
import subprocess
import shutil
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Caminho para as configurações do Nginx e as pastas das aplicações
NGINX_SITES_AVAILABLE = "/etc/nginx/sites-available"
NGINX_SITES_ENABLED = "/etc/nginx/sites-enabled"
APP_DIR = "/var/www"

@app.route('/')
def index():
    apps = []

    for app in os.listdir(NGINX_SITES_AVAILABLE):
        app_path = os.path.join(NGINX_SITES_AVAILABLE, app)
        if os.path.isfile(app_path):
            port = "N/A"
            domain_or_ip = "N/A"

            try:
                # Ler o arquivo de configuração com a codificação apropriada
                with open(app_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        # Buscar a porta
                        if line.startswith("listen"):
                            port = line.split()[1].strip(";")
                        # Buscar o domínio ou IP
                        elif line.startswith("server_name"):
                            domain_or_ip = line.split()[1].strip(";")
            except UnicodeDecodeError:
                # Se UTF-8 falhar, tentar outra codificação
                with open(app_path, "r", encoding="latin1") as f:
                    for line in f:
                        line = line.strip()
                        # Buscar a porta
                        if line.startswith("listen"):
                            port = line.split()[1].strip(";")
                        # Buscar o domínio ou IP
                        elif line.startswith("server_name"):
                            domain_or_ip = line.split()[1].strip(";")
            
            apps.append({"name": app, "port": port, "domain_or_ip": domain_or_ip})
    
    # Obter o status do Nginx
    nginx_status = get_nginx_status()

    return render_template('index.html', apps=apps, nginx_status=nginx_status)

@app.route('/create', methods=['GET', 'POST'])
def create_php_app():
    php_versions = get_php_versions()  # Obter as versões do PHP

    if request.method == 'POST':
        app_name = request.form['app_name']
        php_version = request.form['php_version']
        domain_or_ip = request.form['domain_or_ip']
        port = request.form['port']
        
        # Valor da pasta personalizada (ex: public)
        app_folder_input = request.form['app_folder'].strip()
        
        # Pasta padrão ou personalizada
        app_folder = f"/var/www/{app_name}"
        if app_folder_input:
            app_folder = f"/var/www/{app_name}/{app_folder_input}"

        # Cria a pasta da aplicação, se não existir
        if not os.path.exists(app_folder):
            os.makedirs(app_folder)

        # Configuração do Nginx
        nginx_config = f"""
server {{
    listen {port};
    server_name {domain_or_ip};

    root {app_folder};

    index index.php index.html index.htm;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php{php_version}-fpm.sock;

        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;

        include fastcgi_params;
    }}

    location ~ /\\. {{
        deny all;
    }}
}}
"""
        nginx_file = os.path.join(NGINX_SITES_AVAILABLE, app_name)

        with open(nginx_file, 'w') as f:
            f.write(nginx_config)

        # Criar link simbólico
        subprocess.run(["sudo", "ln", "-s", nginx_file, os.path.join(NGINX_SITES_ENABLED, app_name)])

        # Reiniciar o Nginx
        subprocess.run(["sudo", "systemctl", "restart", "nginx"])

        return redirect(url_for('index'))

    return render_template('create.html', php_versions=php_versions)

@app.route('/delete/<app_name>', methods=['GET', 'POST'])
def delete_php_app(app_name):
    app_folder = os.path.join(APP_DIR, app_name)
    nginx_file = os.path.join(NGINX_SITES_AVAILABLE, app_name)

    if os.path.exists(app_folder) and os.path.exists(nginx_file):
        subprocess.run(["sudo", "rm", os.path.join(NGINX_SITES_ENABLED, app_name)])
        os.remove(nginx_file)
        
        # Exclui o diretório da aplicação
        shutil.rmtree(app_folder)
        
        subprocess.run(["sudo", "systemctl", "restart", "nginx"])

    return redirect(url_for('index'))

@app.route('/nginx/<action>', methods=['GET'])
def nginx_action(action):
    if action == 'stop':
        subprocess.run(["sudo", "systemctl", "stop", "nginx"])
    elif action == 'start':
        subprocess.run(["sudo", "systemctl", "start", "nginx"])
    elif action == 'restart':
        subprocess.run(["sudo", "systemctl", "restart", "nginx"])
    elif action == 'status':
        nginx_status = get_nginx_status()
        return nginx_status

    return redirect(url_for('index'))

def get_php_versions():
    """Obtém as versões do PHP instaladas no sistema"""
    php_paths = ['/usr/bin', '/usr/local/bin']
    versions = set()

    try:
        for path in php_paths:
            for file in os.listdir(path):
                if 'php' in file and '.' in file:
                    version = file.replace('php', '').strip()
                    if version:
                        versions.add(version)

        return sorted(versions) if versions else ["Nenhuma versão do PHP encontrada"]

    except Exception as e:
        print(f"Erro ao obter versões do PHP: {e}")
        return ["Erro ao obter versões do PHP"]


@app.route('/logs/<log_type>')
def nginx_logs(log_type):
    log_file_path = "/var/log/nginx/"
    if log_type == "error":
        log_file_path += "error.log"
    elif log_type == "access":
        log_file_path += "access.log"
    else:
        return "Log inválido!", 400

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            logs = f.readlines()
    except FileNotFoundError:
        logs = ["Arquivo de log não encontrado."]
    except PermissionError:
        logs = ["Permissão negada para acessar os logs."]

    return render_template('logs.html', logs=logs, log_type=log_type)

@app.route('/terminal', methods=['GET', 'POST'])
def terminal():
    command_output = None
    if request.method == 'POST':
        command = request.form['command']
        try:
            # Executa o comando no terminal
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            command_output = result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            command_output = f"Erro ao executar o comando: {e}"

    return render_template('terminal.html', command_output=command_output)

def get_nginx_status():
    """Obtém o status do Nginx"""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'nginx'], stdout=subprocess.PIPE)
        return result.stdout.decode('utf-8').strip()
    except Exception as e:
        return f"Erro ao obter status: {e}"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
