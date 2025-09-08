# sce's cicd server

### how to run
- [ ] get the smee url and discord webhook url from a dev member
- [ ] create a `.env` file like
```
SMEE_URL=https://smee.io/SOME_VALUE_HERE
CICD_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REST_OF_VALUE_HERE
```
- [ ] install smee
```sh
# from within the folder of this project
npm install
```
- [ ] create virtual environment and install python modules
```sh
# from within the folder of this project
python -m venv .venv

source ./.venv/bin/activate

python -m pip install -r requirements.txt
```
- [ ] (if not development) create a config file like
```yml
repos:
  - name: git-workshop
    branch: main
    path: /home/sce/git-workshop
  - name: monitoring
    branch: main
    path: /home/sce/monitoring
```
- [ ] in the same terminal, run the server with
```sh
python server.py --development
```

### for development
- [ ] follow the above steps to setup + the server
- [ ] push small, random commits directly to https://github.com/SCE-Development/git-workshop
- [ ] ensure that the embeds + logs as a result of the above activity


### faq
#### why `"smee-client": "2.0.0"`?
Some machines that we run this on do not have GLIBC_2.28, i.e.
```sh
# npx smee
node: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.28' not found (required by node)
```
version 2.0.0 allows us to use node 16.

#### how do i install python3.10 from source?
```sh
wget https://www.python.org/ftp/python/3.10.4/Python-3.10.4.tgz

tar -xvf Python-3.10.4.tgz

cd Python-3.10.4

# Configure for /usr/local (keeps it separate from system python3.6)
./configure --enable-optimizations

# Build with multiple cores (adjust -j to your CPU count)
make -j$(nproc)

# Install *alongside* system python, don't overwrite
sudo make altinstall

# you should now be able to run python3.10 without issue
python3.10
```
