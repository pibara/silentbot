#!/usr/bin/python3
from lighthive.client import Client
from lighthive.datastructures import Operation
from lighthive.exceptions import RPCNodeException
import dateutil.parser
import datetime
import itertools
import requests
from collections import deque
import time
import json
import sys
import os

class TokenStake:
    def __init__(self, tokens, accounts):
        self.tokens = tokens
        self.accounts = accounts
        self.stake = {}
        for account in self.accounts:
            self.stake[account] = {}
            for token in tokens:
                self.stake[account][token] = 0.0
            self.stake[account]["HIVE"] = 0.0
        self.last_sync = 0
        self.id = 0
        self.url = "https://api.hive-engine.com/rpc/contracts"
        self.json = {
                "jsonrpc": "2.0",
                "id": None,
                "method": "find",
                "params": {
                    "contract": "tokens",
                    "table": "balances",
                    "query": {
                       "account":None,
                       "symbol": None
                    },
                    "limit": 1,
                    "offset": 0,
                    "indexes":[]
                }
            }
        self.sync()
    def sync(self):
        for account in self.accounts:
            for token in self.tokens:
                self.json["params"]["query"]["account"] = account
                self.json["params"]["query"]["symbol"] = token
                self.json["id"] = self.id
                self.id += 1
                try:
                    with requests.post(self.url, json=self.json) as r:
                        data = r.json()
                except:
                    print("Error fetching data from hive-engine")
                    return
                if data['result'] and "stake" in data['result'][0]:
                    self.stake[account][token] = (float(data['result'][0]["stake"]) +
                                                  float(data['result'][0]["delegationsIn"]))
        try:
            props = Client().get_dynamic_global_properties()
            ratio = float(props["total_vesting_shares"].split(" ")[0])/float(props["total_vesting_fund_hive"].split(" ")[0])
            for entry in  [
                    [
                        val["name"],
                        (float(val["vesting_shares"].split(" ")[0]) - 
                            float(val["delegated_vesting_shares"].split(" ")[0]) +
                            float(val["received_vesting_shares"].split(" ")[0])
                        )/ratio
                    ] for val in Client().get_accounts(self.accounts)
                ]:
                self.stake[entry[0]]["HIVE"] = entry[1]
        except RPCNodeException:
            return
        self.last_sync = time.time()
    def __getitem__(self, account):
        if time.time() - self.last_sync > 3500:
            self.sync()
        return self.stake[account]

class Reporter:
    def __init__(self, account, wif, tribe, ts):
        self.account = account
        self.wif = wif
        self.tribe = tribe
        self.ts = ts
        now = datetime.datetime.utcnow()
        self.today = now.date().isoformat()
        self.hour = now.hour
        self.ratings = {}
        self.votes = {}
        self.jicvotes = {}
        self.status = {}
    def tick(self):
        now = datetime.datetime.utcnow()
        if now.date().isoformat() != self.today:
            self.report()
            self.flush()
            self.today = now.date().isoformat()
            self.hour = now.hour
        elif self.hour != now.hour:
            #if (now.hour % 6) == 0:
            self.report()
            self.hour = now.hour
    def report(self):
        users = set()
        now = datetime.datetime.utcnow().time().isoformat().split(".")[0]
        markdown = "# Status report SilentBot " + self.today + " (last update " + now +" UTC)\n\n"
        markdown += """This post is the hourly updated status report for the SilentBot instance that is running on @silentbot. If you want to run your own instance of Silentbot, please contact @pibara.

## Star ratings given by curators today

"""
        for stars in ["5","4","3","2","1"]:
            if stars in self.ratings:
                markdown += "* " + stars + " stars : " + str(len(self.ratings[stars])) + "\n"
            else:
                markdown += "* " + stars + " stars : 0\n"
        markdown += """

## Top-star rated posts

| stars | user | permlink | curator |
| --- | ---  | --- | --- |
"""
        for stars in ["5","4"]:
            if stars in self.ratings:
                for rating in self.ratings[stars]:
                    markdown += "| " + stars + " | @" + rating[0] + " | [" + rating[1] + "](/@" + rating[0] + "/" + rating[1] + ") | @" + rating[2] + " |\n"
                    users.add(rating[0])
        markdown += """

## Voting status

| vote account | vote usage | CCC | HIVE | WIT | 
| --- | --- | --- | --- | --- |
"""
        for account in self.votes:
            users.add(account)
            total = 0.0
            for vote in self.votes[account]:
                total += vote[2]
            percentage = str(int(240*total/(1+self.hour))/100)
            ts = self.ts[account]
            markdown += "| @" + account + " | " + percentage + "% | " + str(int(ts["CCC"])) + " | " + str(int(ts["HIVE"])) + " | " + str(int(ts["WIT"])) +" |\n"
        markdown += """

## Non SilentBot spare-vote voting status

| vote account | vote usage | CCC | HIVE | WIT |
| --- | --- | --- | --- | --- |
"""
        for account in self.jicvotes:
            total = 0.0
            for vote in self.jicvotes[account]:
                total += vote[2]
            percentage = str(int(100*total*2.4/(1+self.hour))/100)
            ts = self.ts[account]
            markdown += "| @" + account + " | " + percentage + "% | " + str(int(ts["CCC"])) + " | " + str(int(ts["HIVE"])) + " | " + str(int(ts["WIT"])) + " |\n"
        markdown += """
## Voting backlog 

| vote account | backlog items | backlog weight | voting strength | effective backlog |
| --- | --- | --- | --- | --- |
"""
        for account in self.status:
            extra = (time.time() - self.status[account][0])/4320
            strength = self.status[account][1] + extra
            if strength > 100:
                strength = 100
            to_hundred = 100 + self.status[account][2]/50 - strength
            effective = str(datetime.timedelta(seconds=to_hundred * 4320))
            markdown += "| @" + account + " | " + str(self.status[account][3]) + " | " + str(self.status[account][2]) + "% | " + str(self.status[account][1]) + "% | " + effective + " |\n"
        markdown += """

<IMG SRC="https://images.hive.blog/p/7b4bio5hobgt1ToxyJNZ2CBe2hrJJxxFumrTYgdiB16dsHGkxy5u76CYzJerHZ2G6dJgNHBvB1d31jsDqMqZ2vG9QHmHKpQKx2vKZW7t7urR4jKE7KYz6uN8MhV6gETX1Ch8Pqp2ejqHPxywbtDHwKJDWJ3g">
"""
        permlink = "status-silentbot-" + self.today
        my_post = Operation('comment', {
                    "parent_author": "",
                    "parent_permlink": self.tribe,
                    "author": self.account,
                    "permlink": permlink,
                    "title": "SilentBob status report " + self.today,
                    "body": markdown,
                    "json_metadata": json.dumps({
                        "tags": [self.tribe, self.account, "curration"],
                        "app": "SilentBot/0.1.4",
                        "users": list(users),
                        "format": "markdown",
                        "image": []
                        })
                })
        resp = None
        while resp is None:
            try:
                resp = Client(keys=[self.wif]).broadcast(my_post)
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
    def flush(self):
        self.ratings = {}
        self.votes = {}
        self.jicvotes = {}
    def rate(self, curator, user, permlink, stars):
        print("REPORTER:RATE", curator, user, permlink, stars)
        ststar = str(stars)
        if ststar not in self.ratings:
            self.ratings[ststar] = []
        self.ratings[ststar].append([user, permlink, curator])
    def vote(self, account, user, permlink, percentage):
        print("REPORTER:VOTE", account, user, permlink, percentage)
        if account not in self.votes:
            self.votes[account] = []
        self.votes[account].append([user, permlink, percentage])
    def jicvote(self, account, user, permlink, percentage):
        print("REPORTER:JICVOTE", account, user, permlink, percentage)
        if account not in self.jicvotes:
            self.jicvotes[account] = []
        self.jicvotes[account].append([user, permlink, percentage])
    def vote_status(self, account, strength, weight, count):
        self.status[account] = [time.time(), strength, weight, count]
    def backup(self):
        obj = {}
        obj["today"] = self.today
        obj["hour"] = self.hour
        obj["ratings"] = self.ratings
        obj["votes"] = self.votes
        obj["jic"]= self.jicvotes
        obj["status"] = self.status
        return obj
    def restore(self, obj):
        if isinstance(obj, dict):
            self.today = obj["today"]
            self.hour = obj["hour"]
            self.ratings = obj["ratings"]
            self.votes = obj["votes"]
            self.jicvotes = obj["jic"]
            self.status = obj["status"]



class Voter:
    def __init__(self, account, wif, reporter):
        self.account = account
        self.wif = wif
        self.reporter = reporter
        self.blacklist = None
        while self.blacklist is None:
            try:
                self.blacklist = {item["name"] for item in Client()("bridge").get_follow_list({"observer":account, "follow_type":"blacklisted"})}
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.following = None
        while self.following is None:
            try:
                self.following = {item["following"] for item in Client().get_following(account)}
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.subscriptions = None
        while self.subscriptions is None:
            try:
                self.subscriptions = {item[0] for item in Client()("bridge").list_all_subscriptions({"account":account})}
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.vote_queue = deque()
        self.just_in_case = deque()
        self.last_vote = 0
    def backup(self):
        obj = {}
        obj["main"] = list(self.vote_queue)
        obj["jic"] = list(self.just_in_case)
        return obj
    def restore(self, obj):
        self.vote_queue = deque(obj["main"])
        self.just_in_case = deque(obj["jic"])
    def candidate_just_in_case(self, author, permlink, tags, ts):
        candidate = False
        if author in self.following:
            candidate = True
        for tag in tags:
            if tag in self.subscriptions:
                candidate = True
        if author in self.blacklist:
            candidate = False
        if candidate:
            self.just_in_case.append([9950, author, permlink, ts])

    def vote_if_needed(self):
        now = time.time()
        while len(self.vote_queue) > 0 and now - self.vote_queue[0][3] > 6*122400:
            candidate = self.vote_queue.popleft()
            print(self.account, "dropping stale vote target, more than 6 days old", candidate[:2])
        while len(self.just_in_case) > 0 and now - self.just_in_case[0][3] > 122400:
            candidate = self.just_in_case.popleft()
            print(self.account, "dropping stale just_in_case candidate, more than 1 days old", candidate[:2])
        while len(self.just_in_case) > 32:
            candidate = self.just_in_case.popleft()
        if now - self.last_vote > 120 and len(self.vote_queue) > 0:
            vp = None
            while vp is None:
                try:
                    vp = Client().account(self.account).vp()
                except RPCNodeException as exp:
                    print(exp)
                    time.sleep(5)
            total_queue_weight = sum([entry[0] for entry in self.vote_queue if entry[0] > 0])/100
            effective_backlog_time = (100 + total_queue_weight/50 - vp) * 4320
            needed = self.vote_queue[0][0]
            if effective_backlog_time < 86400 or needed <= 0:
                attenuation = 1.0
            else:
                attenuation = 1-(effective_backlog_time - 86400)/576000
                print("Attenuate votes to:", attenuation)
            adjusted = int(needed * 100 * attenuation / vp)
            if adjusted <= 10000:
                op = Operation('vote', {
                    "voter": self.account,
                    "author": self.vote_queue[0][1],
                    "permlink": self.vote_queue[0][2],
                    "weight": adjusted,
                })
                try:
                    resp = Client(keys=[self.wif]).broadcast(op)
                    voted_for = self.vote_queue.popleft()
                    print(self.account,"VOTE", vp, adjusted, voted_for)
                    self.reporter.vote(self.account, voted_for[1], voted_for[2], voted_for[0]/100)
                except RPCNodeException as exp:
                    print(self.account,"VOTE ERROR",exp)
                    if "identical" in str(exp):
                        self.vote_queue.popleft()
                        print(self.account,"IDENTICAL")
                    else:
                        print(self.account,"VOTE ERROR:", exp)
                self.last_vote = time.time()
        if now - self.last_vote > 120 and len(self.vote_queue) == 0 and  len(self.just_in_case) > 0:
            vp = None
            while vp is None:
                try:
                    vp = Client().account(self.account).vp()
                except RPCNodeException as exp:
                    print(exp)
                    time.sleep(5)
            needed = self.just_in_case[0][0]
            adjusted = int(needed * 100 / vp)
            if adjusted <= 10000:
                op = Operation('vote', {
                    "voter": self.account,
                    "author": self.just_in_case[0][1],
                    "permlink": self.just_in_case[0][2],
                    "weight": adjusted,
                })
                client = Client(keys=[self.wif])
                try:
                    resp = client.broadcast(op)
                    voted_for = self.just_in_case.popleft()
                    print(self.account,"VOTE", vp, adjusted, voted_for)
                    self.reporter.jicvote(self.account, voted_for[1], voted_for[2], voted_for[0]/100)
                except RPCNodeException as exp:
                    if "identical" in str(exp):
                        self.just_in_case.popleft()
                        print(self.account, "VOTE ERROR: IDENTICAL")
                    else:
                        print("VOTE ERROR:", str(exp))
                self.last_vote = time.time()
        vp = None
        while vp is None:
            try:
                vp = Client().account(self.account).vp()
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.reporter.vote_status(
                self.account,
                vp,
                sum([entry[0] for entry in self.vote_queue if entry[0] > 0])/100,
                len(self.vote_queue))

    def add_to_vote_queue(self, strength, author, permlink, ts):
        queueweight = (sum([entry[0] for entry in self.vote_queue]) + strength)/100000
        if queueweight > 1:
            vote_strength = int(strength/queueweight)
            print("Voting queue over full, downgrading vote from", strength, "to", vote_strength)
        else:
            vote_strength = strength
        self.vote_queue.append([vote_strength, author, permlink, ts]) 
            


class Responder:
    def __init__(self, account, wif, blacklist, lookup, tribe, tags, reporter):
        self.account = account
        self.wif = wif
        self.blacklist = blacklist
        self.lookup = lookup
        self.tribe = tribe
        self.tags = tags
        self.non_curator = set()
        self.tag_abusers = {}
        self.spammer = set()
        self.reporter = reporter

    def backup(self):
        rval = {}
        rval["noncur"] = list(self.non_curator)
        rval["tag_abuse"] = self.tag_abusers
        rval["spam"] = list(self.spammer)
        return rval

    def restore(self, obj):
        if "noncur" in obj:
            self.non_curator = set(obj["noncur"])
        if "tag_abuse" in obj:
            self.tag_abusers = obj["tag_abuse"]
        if "spam" in obj:
            self.spammer = set(obj["spam"])

    def star(self, comment, post, star_count, voters, curator):
        if post[0] in self.blacklist:
            self.is_blacklisted(comment, post)
            return
        original_post = None
        while original_post is None:
            try:
                original_post = Client()("bridge").get_post({"author": post[0], "permlink": post[1]})
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        if "json_metadata" in original_post and isinstance(original_post["json_metadata"], dict) and "tags" in original_post["json_metadata"] and isinstance(original_post["json_metadata"]["tags"], list) and self.tribe in original_post["json_metadata"]["tags"]:
            if "created" in original_post:
                ts = dateutil.parser.parse(original_post["created"]).timestamp()
            else:
                ts = 0
            has_tag = False
            for tag in self.tags:
                if tag in original_post["json_metadata"]["tags"]:
                    has_tag = True
            if has_tag:
                our_comment_permlink  = "-".join(post[0].split(".")) + "-" + post[1] + "-" + self.account
                try:
                    our_comment = Client().get_content(self.account, our_comment_permlink)
                    return
                except:
                    pass
                power_up = "percent_hbd" in original_post and original_post["percent_hbd"] == 0
                if star_count > 5:
                    star_count = 5
                if star_count < 1:
                    star_count = 1
                config = self.lookup[power_up][star_count]
                body = '<A HREF="' + config["link"] + '"><IMG SRC="' + config["icon"] + '"></A>'
                my_post = Operation('comment', {
                    "parent_author": post[0],
                    "parent_permlink": post[1],
                    "author": self.account,
                    "permlink": our_comment_permlink,
                    "title": "silentbob star comment",
                    "body": body,
                    "json_metadata": json.dumps({
                        "tags": [self.tribe, self.account, "curration"],
                        "app": "SilentBot 0.1.3"
                        })
                })
                resp = None
                while resp is None:
                    try:
                        resp = Client(keys=[self.wif]).broadcast(my_post)
                    except RPCNodeException as exp:
                        print(exp)
                        time.sleep(5)
                self.reporter.rate(curator, post[0], post[1], star_count)
                for voter in voters:
                    voter.add_to_vote_queue(config["percentage"], post[0], post[1], ts)
            else:
                self.no_tag_post(comment)
        else:
            self.not_a_tribe_post(comment)

    def spam(self, post, voters):
        if post[0] in self.spammer:
            percentage = -10000
        else:
            percentage = -5000
        original_post = None
        while original_post is None:
            try:
                original_post = Client()("bridge").get_post({"author": post[0], "permlink": post[1]})
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        if "created" in original_post:
            ts = dateutil.parser.parse(original_post["created"]).timestamp()
        else:
            ts = 0
        our_comment_permlink  = "-".join(post[0].split(".")) + "-" + post[1] + "-" + self.account
        try:
            our_comment = Client().get_content(self.account, our_comment_permlink)
            return
        except:
            pass
        config = self.lookup[0][0]
        body = '<A HREF="' + config["link"] + '"><IMG SRC="' + config["icon"] + '"></A>'
        my_post = Operation('comment', {
            "parent_author": post[0],
            "parent_permlink": post[1],
            "author": self.account,
            "permlink": our_comment_permlink,
            "title": "silentbob star comment",
            "body": body,
            "json_metadata": json.dumps({
                        "tags": [self.tribe, self.account, "curration"],
                        "app": "SilentBot 0.1.3"
                        })
        })
        resp = None
        while resp is None:
            try:
                resp = Client(keys=[self.wif]).broadcast(my_post)
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        for voter in voters:
            voter.add_to_vote_queue(percentage, post[0], post[1], ts)
        self.spammer.add(post[0])

    def tag_abuse(self, post, voters):
        if post[0] in self.tag_abusers:
            ta_count = self.tag_abusers[post[0]] + 1
        else:
            ta_count = 1
        if ta_count > 5:
            percentage = -2500
        elif ta_count > 1:
            percentage = -1000
        else:
            percentage = -100
        original_post = None
        while original_post is None:
            try:
                original_post = Client()("bridge").get_post({"author": post[0], "permlink": post[1]})
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        if "created" in original_post:
                ts = dateutil.parser.parse(original_post["created"]).timestamp()
        else:
            ts = 0
        our_comment_permlink  = "-".join(post[0].split(".")) + "-" + post[1] + "-" + self.account
        try:
            our_comment = Client().get_content(self.account, our_comment_permlink)
            return
        except:
            pass
        config = self.lookup[1][0]
        body = '<A HREF="' + config["link"] + '"><IMG SRC="' + config["icon"] + '"></A>'
        my_post = Operation('comment', {
            "parent_author": post[0],
            "parent_permlink": post[1],
            "author": self.account,
            "permlink": our_comment_permlink,
            "title": "silentbob star comment",
            "body": body,
            "json_metadata": json.dumps({
                        "tags": [self.tribe, self.account, "curration"],
                        "app": "SilentBot 0.1.3"
                        })
        })
        resp = None
        while resp is None:
            try:
                resp = Client(keys=[self.wif]).broadcast(my_post)
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        for voter in voters:
            voter.add_to_vote_queue(percentage, post[0], post[1], ts)
        self.tag_abusers[post[0]] = ta_count
    def respond(self, comment, body):
        our_comment_permlink  = "-".join(comment[0].split(".")) + "-" + comment[1] + "-" + self.account
        try:
            our_comment = Client().get_content(self.account, our_comment_permlink)
            return
        except:
            pass
        post = Operation('comment', {
                        "parent_author": comment[0],
                        "parent_permlink": comment[1],
                        "author": self.account,
                        "permlink": our_comment_permlink,
                        "title": "silentbob star comment",
                        "body": body,
                        "json_metadata": json.dumps({
                          "tags": [self.tribe, self.account, "curration"],
                          "app": "SilentBot 0.1.3"
                        })
                    })
        resp = None
        while resp is None:
            try:
                resp = Client(keys=[self.wif]).broadcast(post)
            except RPCNodeException as exp:
                print(exp)

    def not_a_currator(self, comment):
        if comment[0] not in self.non_curator:
            self.non_curator.add(comment[0])
            return self.respond(comment,"I'm terribly sorry, but I don't recognize you as a Silent Bob curator")

    def is_blacklisted(self, comment, post):
        body = "I'm really sorry for the inconvenience, but one of the Silent Bob curators has blacklisted @" + post[0]
        self.respond(comment, body)

    def not_a_tribe_post(self, comment):
        body = "My appologies for the inconvenience, but this is not a tribe post in the " + self.tribe + " tribe"
        self.respond(comment, body)

    def no_tag_post(self, comment):
        body = "I'm sorry, curator, but this instance of the Silent Bob curation bot will only allow you to curate #" + self.tribe + " posts with at least one of the followint tags: "
        for tag in self.tags:
            body += " #" + tag
        self.respond(comment, body)

    def mention(self, post, comment, body, voters, curators):
        print("####################", self.account, "######################")
        parts = body.split("@" + self.account)
        if len(parts) == 2:
            cmd = parts[1].split(" ")[1:3]
            if len(cmd) == 2:
                print("Formatted as command")
                command = cmd[0].lower()
                if command == "star":
                    try:
                        star_count = int(cmd[1])
                    except ValueError:
                        print("Star with non number")
                        return
                    if comment[0] in curators:
                        return self.star(comment, post, star_count, voters, comment[0])
                    else:
                        return self.not_a_currator(comment)
                if command == "abuse":
                    abusetype = cmd[1].lower()
                    if abusetype == "spam":
                        if comment[0] in curators:
                            return self.spam(post, voters)
                        else:
                            return self.not_a_currator(comment)
                    elif abusetype == "tag":
                        if comment[0] in curators:
                            return self.tag_abuse(post, voters)
                        else:
                            return self.not_a_currator(comment)
        return

class SilentBot:
    def __init__(self, bot_account, wif_map, curators, voters):
        self.bot_account = bot_account
        self.curator_names = set(curators)
        lupath = os.path.join(os.path.dirname(os.path.realpath(__file__)),"sb-lookup.json")
        with open(lupath) as lufil:
            lup = json.load(lufil)
        lookup = lup["responses"]
        tribe = lup["tribe"]
        tags = lup["tags"]
        self.ts = TokenStake(["CCC","WIT"], voters + [bot_account])
        self.reporter = Reporter(bot_account, wif_map[bot_account], tribe, self.ts)
        self.voters = [Voter(item, wif_map[item], self.reporter) for item in voters]
        self.voters.append(Voter(bot_account, wif_map[bot_account], self.reporter))
        self.responder = Responder(
                bot_account,
                wif_map[bot_account],
                set(itertools.chain().from_iterable([voter.blacklist for voter in self.voters])),
                lookup,
                tribe,
                tags,
                self.reporter)
        if "SILENTBOT_DATA_DIR" in os.environ:
            self.bupath = os.path.join(os.environ["SILENTBOT_DATA_DIR"], "sb-backup.json")
        else:
            self.bupath = os.path.join(os.path.dirname(os.path.realpath(__file__)),"sb-backup.json")
        self.headno = None
        while self.headno is None:
            try:
                self.headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.headno_age = time.time()
        self.next = self.headno - 100
        self.restore()

    def sync(self):
        obj = dict()
        obj["block"] = self.next
        obj["voters"] = dict()
        for voter in self.voters:
            obj["voters"][voter.account] = voter.backup()
        obj["responder"] = self.responder.backup()
        obj["reporter"] = self.reporter.backup()
        with open(self.bupath, "w") as outfil:
            json.dump(obj, outfil)

    def restore(self):
        try:
            with open(self.bupath) as infil:
               obj = json.load(infil)
        except FileNotFoundError:
            self.sync()
            with open(self.bupath) as infil:
               obj = json.load(infil)
        self.next = obj["block"]
        if "voters" in obj:
            for voter in self.voters:
                if voter.account in obj["voters"]:
                    voter.restore(obj["voters"][voter.account])
        if "responder" in obj:
            self.responder.restore(obj["responder"])
        if "reporter" in obj:
            self.reporter.restore(obj["reporter"])

    def upto_head(self):
        processed = 0
        self.headno = None
        while self.headno is None:
            try:
                self.headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        start_time = time.time()
        rval = 0
        blocks_left = self.headno + 1 - self.next
        while blocks_left !=0:
            if blocks_left > 100:
                count = 100
                blocks_left -= 100
            else:
                count = blocks_left
                blocks_left = 0
            blocks = None
            while blocks is None:
                try:
                    blocks = Client()('block_api').get_block_range({"starting_block_num": self.next, "count":count})["blocks"]
                except RPCNodeException as exp:
                    print(exp)
                    time.sleep(5)
            for block in blocks:
                ts = dateutil.parser.parse(block["timestamp"]).timestamp()
                if "transactions" in block:
                    for trans in block["transactions"]:
                        if "operations" in  trans:
                            for operation in  trans["operations"]:
                                op_type = operation["type"]
                                vals = operation["value"]
                                if op_type == "comment_operation":
                                    if vals["parent_author"]:
                                        mentioned = False
                                        if vals["json_metadata"]:
                                            cust = json.loads(vals["json_metadata"])
                                            if "users" in cust and self.bot_account in cust["users"]:
                                                mentioned = True
                                                self.responder.mention([vals["parent_author"], vals["parent_permlink"]],
                                                                       [vals["author"], vals["permlink"]],
                                                                       vals["body"],
                                                                       self.voters,
                                                                       self.curator_names)
                                        if not mentioned and vals["body"].startswith("@" + self.bot_account + " "):
                                            self.responder.mention([vals["parent_author"], vals["parent_permlink"]],
                                                                       [vals["author"], vals["permlink"]],
                                                                       vals["body"],
                                                                       self.voters,
                                                                       self.curator_names)
                                    else:
                                        if vals["json_metadata"]:
                                            ok = False
                                            try:
                                                cust = json.loads(vals["json_metadata"])
                                            except json.decoder.JSONDecodeError:
                                                cust = {}
                                            if "app" in cust and "tags" in cust:
                                                ok = True
                                                for prefix in ["exhaust", "3speak", "VIMM", "aureal", "actifit"]:
                                                    if cust["app"].startswith(prefix):
                                                        ok = False
                                            if ok:
                                                for voter in self.voters:
                                                    voter.candidate_just_in_case(vals["author"], vals["permlink"], cust["tags"], ts)
                    self.next +=1
                    rval += 1
            processed += count
            total_time = time.time() - start_time
            speed = processed/total_time
            if blocks_left > 0:
                self.headno = None
                while self.headno is None:
                    try:
                        self.headno = Client().get_dynamic_global_properties()["head_block_number"]
                    except RPCNodeException as exp:
                        print(exp)
                        time.sleep(5)
                blocks_left = self.headno + 1 - self.next
            time_left = blocks_left/speed
            print("BLOCK:", self.next-1, self.headno ,count,"processed", blocks_left, "left to go", int(speed),"blocks per second", int(time_left/60), "minutes to catch up.")
            for voter in self.voters:
                voter.vote_if_needed()
            self.sync()
        return rval

    def run(self):
        lastsync = 0
        while True:
            count = self.upto_head()
            self.reporter.tick()
            sleeptime = 120 - count
            if sleeptime > 0:
                time.sleep(sleeptime)
            

if __name__ == "__main__":
    lupath = os.path.join(os.path.dirname(os.path.realpath(__file__)),"sb-lookup.json")
    with open(lupath) as lufil:
        lup = json.load(lufil)
    bot_account = lup["bot"]
    voters = lup["voters"]
    curators = lup["curators"]
    wif_map = dict()
    if not bot_account.upper() + "_WIF" in os.environ:
        print("ERROR:", bot_account.upper() + "_WIF environment variable not set!")
        sys.exit(1)
    wif_map[bot_account] = os.environ[bot_account.upper() + "_WIF"]
    for voter in voters:
        if not voter.upper() + "_WIF" in os.environ:
            print("ERROR:", voter.upper() + "_WIF environment variable not set!")
            sys.exit(1)
        wif_map[voter] = os.environ[voter.upper() + "_WIF"]
    bot = SilentBot(bot_account, wif_map, curators, voters)
    bot.run()
