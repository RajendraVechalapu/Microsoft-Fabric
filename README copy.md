python -m venv rajenv

pip freeze > requirements.txt
#ensure remove install from requirements.txt after freeze command

.\rajenv\Scripts\activate

$env:FLASK_APP = "myapp"
flask run --reload

pip install -r requirements.txt


--Uninstalls
pip list
pip freeze > unins ; pip uninstall -y -r unins ; del unins
