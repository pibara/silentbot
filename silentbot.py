#!/usr/bin/python3
from lighthive.client import Client
from lighthive.datastructures import Operation
from lighthive.exceptions import RPCNodeException
from collections import deque
import time
import json
import sys
import os
# TODO:
# * Support abuse commands
#   * abuse spam
#   * abuse wtf
#   * abuse tag
# * Support blacklists config
# * Maintain own blacklist
# * Respond to non-curators once
# * Respond to curators responding to wrong tag pair
# * Respond to curators giving invalid commands


class SilentBot:
    def __init__(self, bot_account, wif_map, curators):
        self.hive = dict()
        self.wif_map = wif_map
        for key in wif_map:
            self.hive[key] = Client(keys=[wif_map[key]])
        if "SILENTBOT_DATA_DIR" in os.environ:
            self.bupath = os.path.join(os.environ["SILENTBOT_DATA_DIR"], "backup.json")
        else:
            self.bupath = os.path.join(os.path.dirname(os.path.realpath(__file__)),"backup.json")
        self.bot_account = bot_account
        self.interval = 3
        self.headno = self.hive[bot_account].get_dynamic_global_properties()["head_block_number"]
        self.headno_age = time.time()
        self.next = self.headno - 100
        self.curators = curators
        self.vote_queue = dict()
        self.vote_queue_weight = dict()
        for key in wif_map:
            self.vote_queue[key] = deque()
            self.vote_queue_weight[key] = 0
        self.restore()
        for key in wif_map:
            if key not in self.vote_queue:
                self.vote_queue[key] = deque()
                self.vote_queue_weight[key] = 0
        self.blacklist = set()
        for account in curators:
            entries = self.hive[bot_account]("bridge").get_follow_list({"observer":account, "follow_type":"blacklisted"})
            for entry in entries:
                if "name" in entry:
                    self.blacklist.add(entry["name"])
        print("BLACKLIST:", self.blacklist)
        lupath = os.path.join(os.path.dirname(os.path.realpath(__file__)),"lookup.json") 
        with open(lupath) as lufil:
            self.lookup = json.load(lufil)

    def sync(self):
        print("SYNC")
        obj = dict()
        obj["block"] = self.next
        obj["pending"] = dict()
        for key in self.vote_queue:
            obj["pending"][key] = list(self.vote_queue[key])
        obj["weight"] = self.vote_queue_weight
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
        self.vote_queue_weight = obj["weight"]
        self.vote_queue = dict()
        for key in obj["pending"]:
            self.vote_queue[key] = deque(obj["pending"][key])

    def star(self, author, permlink, star_count):
        done = False
        count = 0
        while not done:
            try:
                our_comment_permlink  = "-".join(author.split(".")) + "-" + permlink + "-" + self.bot_account
                try:
                    our_comment = self.hive[self.bot_account].get_content(self.bot_account, our_comment_permlink)
                    comment_exists = True
                except:
                    comment_exists = False
                if not comment_exists:
                    comment = self.hive[self.bot_account].get_content(author, permlink)
                    power_up = int(comment["percent_hbd"] == 0)
                    if star_count > 5:
                        star_count = 5
                    if star_count < 1:
                        star_count = 1
                    config = self.lookup[power_up][star_count]
                    body = '<A HREF="' + config["link"] + '"><IMG SRC="' + config["icon"] + '"></A>'
                    post = Operation('comment', {
                        "parent_author": author,
                        "parent_permlink": permlink,
                        "author": self.bot_account,
                        "permlink": our_comment_permlink,
                        "title": "silentbob star comment",
                        "body": body,
                        "json_metadata": json.dumps({"tags": self.bot_account + " creativecoin"})
                    })
                    resp =self.hive[self.bot_account].broadcast(post)
                    print("STAR", star_count, power_up, author, permlink, config["percentage"])
                    for key in self.vote_queue:
                        self.vote_queue[key].append([config["percentage"], author, permlink])
                        self.vote_queue_weight[key] += config["percentage"]/100
                else:
                    print("NOTICE: Not doing second comment for single post") 
                done=True
                count = 0
            except RPCNodeException as exp:
                count += 1
                print("RPCNode exception during star",count, exp)
                time.sleep(10)
                self.hive[self.bot_account] = Client(keys=[self.wif_map[self.bot_account]])

    def invocation(self, author, permlink, body):
        parts = body.split("@" + self.bot_account)
        if len(parts) == 2:
            cmd = parts[1].split(" ")[1:3]
            if len(cmd) == 2:
                command = cmd[0].lower()
                if command == "star":
                    try:
                        star_count = int(cmd[1])
                    except ValueError:
                        return
                    return self.star(author, permlink, star_count)
                if command == "abuse":
                    return
        return

    def upto_head(self):
        rval = 0
        blocks_left = self.headno + 1 - self.next
        while blocks_left !=0:
            if blocks_left > 100:
                count = 100
                blocks_left -= 100
            else:
                count = blocks_left
                blocks_left = 0
            try:
                blocks = self.hive[self.bot_account]('block_api').get_block_range({"starting_block_num": self.next, "count":count})["blocks"]
                for block in blocks:
                    if "transactions" in block:
                        for trans in block["transactions"]:
                            if "operations" in  trans:
                                for operation in  trans["operations"]:
                                    op_type = operation["type"]
                                    vals = operation["value"]
                                    if op_type == "comment_operation":
                                        if vals["parent_author"]:
                                            if vals["json_metadata"]:
                                                cust = json.loads(vals["json_metadata"])
                                                if "users" in cust and self.bot_account in cust["users"] and vals["author"] in self.curators:
                                                    self.invocation(vals["parent_author"], vals["parent_permlink"], vals["body"])
                    self.next +=1
                    rval += 1
            except RPCNodeException as exp:
                print("RPCNodeException during upto_head",exp)
                time.sleep(10)
                self.hive[self.bot_account] = Client(keys=[self.wif_map[self.bot_account]])
            print("BLOCK:", self.next-1, count)
        return rval

    def votable(self, account):
        if self.vote_queue_weight[account] < 500:
            percentage = 99.5
        elif self.vote_queue_weight[account] < 1000:
            percentage = 99.5 - (self.vote_queue_weight[account] - 500) / 25
        if percentage < 10:
            percentage = 10
        return percentage

    def vote_if_needed(self):
        rval = False
        for key in self.vote_queue:
            try:
                self.hive[key] = Client(keys=[self.wif_map[key]])
                if self.vote_queue[key]:
                    self.hive[key] = Client(keys=[self.wif_map[key]])
                    vp = self.hive[key].account(key).vp() 
                    treshold = self.votable(key)
                    if vp >= treshold:
                        action = self.vote_queue[key].popleft()
                        percentage = action[0]
                        author = action[1]
                        permlink = action[2]
                        self.vote_queue_weight[key] -= percentage/100
                        print("VOTE:", key, percentage, author, permlink)
                        op = Operation('vote', {
                            "voter": key,
                            "author": author,
                            "permlink": permlink,
                            "weight": percentage,
                        })
                        resp = self.hive[key].broadcast(op)
                        rval = True
                    else:
                        duration = time.strftime('%H:%M', time.gmtime(int((treshold-vp)*4320)))
                        print("Waiting for more voting power for", key, "in", duration,";", vp, "<", treshold)
            except RPCNodeException as ex:
                print("RPCNodeException during vote_if_needed", ex)
                time.sleep(5)
                self.hive[key] = Client(keys=[self.wif_map[key]])
        return rval
            
    def run(self):
        lastsync = 0
        while True:
            count = self.upto_head()
            if count == 0:
                time.sleep(self.interval*10)
            try:
                voted = self.vote_if_needed()
                if voted or count:
                    self.sync()
                old_head = self.headno
                self.hive[self.bot_account] = Client(keys=[self.wif_map[self.bot_account]])
                self.headno = self.hive[self.bot_account].get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                print("RPCNodeException during run", exp)
                time.sleep(10)
                self.hive[self.bot_account] = Client(keys=[self.wif_map[self.bot_account]])




if __name__ == "__main__":
    bot_account = "silentbot"
    wif_map = dict()
    curators = list()
    if sys.argv[0] in ["python", "python3"]:
        sys.argv = sys.argv[1:]
    if len(sys.argv) > 1:
        if sys.argv[1].upper() + "_WIF" in os.environ:
            bot_account = sys.argv[1]
        else:
            curators.append(sys.argv[1])
    if not bot_account.upper() + "_WIF" in os.environ:
        print("ERROR:", bot_account.upper() + "_WIF environment variable not set!")
        sys.exit(1)
    wif_map[bot_account] = os.environ[bot_account.upper() + "_WIF"]
    if len(sys.argv) > 2:
        for other_account in sys.argv[2:]:
            if other_account.upper() + "_WIF" in os.environ:
                wif_map[other_account] = os.environ[other_account.upper() + "_WIF"]
            curators.append(other_account)
    bot = SilentBot(bot_account, wif_map, curators)
    bot.run()
