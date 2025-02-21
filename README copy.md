python -m venv rajenv

pip freeze > requirements.txt
#ensure remove install from requirements.txt after freeze command

.\rajenv\Scripts\activate
$env:DATABASE_URL = "postgresql://rajpostgressql_user:QfEIQR6tHAfUWFSwIIUxhmlAd4ozL0lZ@dpg-cma94evqd2ns73bd3bmg-a.oregon-postgres.render.com/rajpostgressql"
$env:FLASK_APP = "myapp"
flask run --reload

pip install -r requirements.txt


--Uninstalls
pip list
pip freeze > unins ; pip uninstall -y -r unins ; del unins
