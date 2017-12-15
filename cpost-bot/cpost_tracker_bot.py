'''
Created on Dec 14, 2017

@author: jmartan
'''
from pprint import pprint
import requests
import json
from flask import Flask
from flask import request

# local configuration
import config as cfg

spk_headers = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
    "Authorization": "Bearer " + cfg.bot_access_token
}
spark_api_root_url = "https://api.ciscospark.com/v1"

app = Flask(__name__)
app.config["DEBUG"] = True
webhook_url = None
bot_name = cfg.bot_name
bot_email = cfg.bot_email
requests.packages.urllib3.disable_warnings()


def send_spark_get(url, payload=None, js=True):

    full_url = spark_api_root_url + url
    if payload == None:
        request = requests.get(full_url, headers=spk_headers)
    else:
        request = requests.get(full_url, headers=spk_headers, params=payload)
    if js == True:
        request = request.json()
    return request


def send_spark_post(url, data, js=True):

    full_url = spark_api_root_url + url
    request = requests.post(full_url, json.dumps(data), headers=spk_headers)
    if js == True:
        request = request.json()
    return request


def send_spark_put(url, data, js=True):

    full_url = spark_api_root_url + url
    request = requests.put(full_url, json.dumps(data), headers=spk_headers)
    if js == True:
        request = request.json()
    return request


def send_spark_delete(url):

    full_url = spark_api_root_url + url
    request = requests.delete(full_url, headers=spk_headers)
    return request


def create_webhook(target_url):
    webhooks = {}
    resources = ["messages", "memberships"]
    webhook_name = "Webhook for Bot"
    event = "created"
    status = None
        
    check_webhook = send_spark_get("/webhooks", js=False)
    if check_webhook.status_code == 200:
        webhook_data = check_webhook.json()
        if len(webhook_data["items"]) > 0:
            for items in webhook_data["items"]:
                webhooks[items["id"]] = [items["id"], items["resource"]]
    if len(webhooks) > 0:
        for webhook_id in webhooks:
            del_res = send_spark_delete("/webhooks/" + webhook_id)
            if del_res.status_code == 204:
                app.logger.info("Webhook was removed")
            else:
                app.logger.info("Webhook {} delete failed, code: {}.".format(webhook_id, del_res.status_code))
        
    for resource in resources:
        webhook_data = {
            "name": webhook_name,
            "targetUrl": target_url,
            "resource": resource,
            "event": event}
        webhook_res = send_spark_post("/webhooks", webhook_data, js=False)
        if webhook_res.status_code == 200:
            status = True
            app.logger.info("Webhook was successfully created")
        else:
            status = False
            app.logger.error(
            "Something went wrong. I was unable to create the webhook: {}".format(webhook_res.reason))
            
    return status


def greetings(personal=True):
    
    greeting_msg = """
Dobrý den, mým úkolem je poskytovat informace o zásilkách České pošty.
"""
    if not personal:
        greeting_msg += """
Nezapomeňte, že je třeba mne oslovit '@{}'
""".format(bot_name)

    return greeting_msg


def help_me(personal=True):

    greeting_msg = """
Napište mi číslo zásilky, o které chcete informace. Můžete poslat i více čísel, oddělených mezerou.
"""
    if not personal:
        greeting_msg += """
Nezapomeňte, že je třeba mne oslovit '@{}'
""".format(bot_name)

    return greeting_msg


def get_parcel_info(parcel_id):
    info_url = "https://b2c.cpost.cz/services/ParcelHistory/getDataAsJson?idParcel={}".format(parcel_id)
    
    res = requests.get(info_url, verify=False)
#     result = ("Chyba v komunikaci se serverem b2c.cpost.cz: {}".format(res.status_code))
    result = None
    if res.status_code == 200:
        result = res.json()
    
    return result


def format_parcel_status(status, accepted_ids=()):

    parcel_format = ""
    id_is_num = False
    try:
        int(status.get("id"))
        id_is_num = True
    except ValueError:
        pass

    if id_is_num or (status.get("id") in accepted_ids):
        parcel_format = "{} --> {}".format(status.get("date"), status.get("text"))
        if (status.get("postcode") is not None) and (status.get("postoffice") is not None):
            parcel_format += " ({} - {})".format(status.get("postcode"), status.get("postoffice"))

    return parcel_format


def is_room_direct(room_id):
    res = send_spark_get("/rooms/" + room_id, js=False)
    if res.status_code == 200:
        data = res.json()
        return data["type"] == "direct"
    else:
        app.logger.error("Room info request failed: {}".format(res.status_code))
    
    return False


@app.before_first_request
def startup():
    global bot_email, bot_name
    
    if len(cfg.bot_access_token) != 0:
        test_auth = send_spark_get("/people/me", js=False)
        if test_auth.status_code == 401:
            app.logger.error("Looks like provided access toke is not correct. \n"
                  "Please review it and make sure it belongs to your bot account.\n"
                  "Do not worry if you have lost the access token. "
                  "You can always go to https://developer.ciscospark.com/apps.html "
                  "URL and generate a new access token.")
        elif test_auth.status_code == 200:
            test_auth = test_auth.json()
            bot_name = test_auth.get("displayName", "")
            bot_email = test_auth.get("emails", "")[0]
            test_auth = send_spark_get("/people/me", js=False)
    else:
        app.logger.error("'cfg.bot_access_token' variable is empty! \n"
              "Please populate it with bot's access token and run the script again.\n"
              "Do not worry if you have lost the access token. "
              "You can always go to https://developer.ciscospark.com/apps.html "
              "URL and generate a new access token.")

    if "@sparkbot.io" not in bot_email:
        app.logger.error("You have provided access token which does not belong to your bot.\n"
              "Please review it and make sure it belongs to your bot account.\n"
              "Do not worry if you have lost the access token. "
              "You can always go to https://developer.ciscospark.com/apps.html "
              "URL and generate a new access token.")


@app.route('/', methods=['GET', 'POST'])
def spark_webhook():
    if request.method == 'POST':
        webhook = request.get_json(silent=True)
        if webhook['data']['personEmail'] != bot_email:
            pprint(webhook)
        if webhook['resource'] == "memberships" and webhook['data']['personEmail'] == bot_email:
            personal_room = is_room_direct(webhook['data']['roomId'])
            send_spark_post("/messages",
                            {
                                "roomId": webhook['data']['roomId'],
                                "markdown": greetings(personal_room)
                            }
                            )
        msg = None
        if "@sparkbot.io" not in webhook['data']['personEmail']:
            result = send_spark_get(
                '/messages/{0}'.format(webhook['data']['id']))
            in_message = result.get('text', '').lower()
            in_message = in_message.replace(bot_name.lower() + " ", '')
            if 'help' in in_message:
                personal_room = is_room_direct(webhook['data']['roomId'])
                msg = help_me(personal_room)
            else:
                for parcel_id in in_message.split():
                    parcel_data = get_parcel_info(parcel_id)
                    parcel_history = []
                    for status in parcel_data[0].get("states").get("state"):
                        hist_data = format_parcel_status(status, ("-B", "-I", "-F"))
                        if hist_data != "":
                            parcel_history.append(hist_data)

                    msg = """
Zásilka: **{}**  
Aktuální stav: **{}**  
Historie:  
{}
""".format(parcel_data[0].get("id"), parcel_history[-1], "  \n".join(parcel_history[0:-1]))

            if msg != None:
                send_spark_post("/messages",
                                {"roomId": webhook['data']['roomId'], "markdown": msg})
        return "true"
    elif request.method == 'GET':
        message = "<center><img src=\"http://bit.ly/SparkBot-512x512\" alt=\"Spark Bot\" style=\"width:256; height:256;\"</center>" \
                  "<center><h2><b>Congratulations! Your <i style=\"color:#ff8000;\">%s</i> bot is up and running.</b></h2></center>" % bot_name
                  
        message += "<center><b>I'm hosted at: <a href=\"{0}\">{0}</a></center>".format(request.url)
        if webhook_url is None:
            res = create_webhook(request.url)
            if res is True:
                message += "<center><b>New webhook created sucessfully</center>"
            else:
                message += "<center><b>Tried to create a new webhook but failed, see application log for details.</center>"

        return message


if __name__ == "__main__":
    app.run(host='localhost', port=8080)
