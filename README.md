# sce's cicd server

### how to run
- [ ] get the smee url and discord webhook url from a dev member
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
- [ ] in the same terminal, run the server with
```sh
python server.py --development
```
