
import json
import datetime
from uuid import uuid4
from functools import cache, lru_cache
from async_lru import alru_cache
import asyncio
from pathlib import Path
 
from selenium import webdriver
from seleniumwire import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
 
import getpass
import aiohttp
import requests
 
class DBWriter:
    def __init__(self, username="john.newbie@world.com", password="john.newbie@world.com"):
        self.username = username
        self.password = password
        self.token = None
        pass
 
    async def getToken(self):
        # keyurl = "http://host.docker.internal:33001/oauth/login3"
        if self.token:
            return self.token
       
        keyurl = "http://localhost:33001/oauth/login3"
        async with aiohttp.ClientSession() as session:
            async with session.get(keyurl) as resp:
                # print(resp.status)
                keyJson = await resp.json()
                # print(keyJson)
 
            payload = {"key": keyJson["key"], "username": self.username, "password": self.password}
            async with session.post(keyurl, json=payload) as resp:
                # print(resp.status)
                tokenJson = await resp.json()
                # print(tokenJson)
        self.token = tokenJson.get("token", None)
        return self.token
 
    async def queryGQL(self, query, variables):
        # gqlurl = "http://host.docker.internal:33001/api/gql"
        gqlurl = "http://localhost:33001/api/gql"
        token = self.token
        if token is None:
            token = await self.getToken()
        payload = {"query": query, "variables": variables}
        # headers = {"Authorization": f"Bearer {token}"}
        cookies = {'authorization': token}
        async with aiohttp.ClientSession() as session:
            # print(headers, cookies)
            async with session.post(gqlurl, json=payload, cookies=cookies) as resp:
                # print(resp.status)
                if resp.status != 200:
                    text = await resp.text()
                    print(f"failed query \n{query}\n with variables {variables}".replace("'", '"'))
                    print(f"failed resp.status={resp.status}, text={text}")
                    raise Exception(f"Unexpected GQL response", text)
                else:
                    response = await resp.json()
                    return response  
               
    async def queryGQL3(self, query, variables):
        times = 3
        result = None
        for i in range(times):
            try:
                result = await self.queryGQL(query=query, variables=variables)
                if result.get("errors", None) is None:
                    return result
                print(result)
            except Exception:
                pass
 
            await asyncio.sleep(10)
               
        raise Exception(f"unable to run query={query} with variables {variables} for {times} times\n{result}".replace("'", '"'))
 
    @cache
    def GetQuery(self, tableName, queryType):
        assert queryType in ["read", "readp", "create", "update"], f"unknown queryType {queryType}"
        queryfile = f"./gqls/{tableName}/{queryType}.gql"
        # querySet = self.GetQuerySet(tableName=tableName)
        # query = querySet.get(queryType, None)
        with open(queryfile, "r", encoding="utf-8") as fi:
            lines = fi.readlines()
        query = ''.join(lines)
        assert query is not None, f"missing {queryType} query for table {tableName}"
        return query
 
    @alru_cache(maxsize=1024)
    async def asyncTranslateID(self, outer_id, type_id):
        """prevede vnejsi id na vnitrni id pro dany typ,
        napr id (UCO) na id odpovidajici entity v nasem systemu
        """
       
        query = 'query($type_id: UUID!, $outer_id: String!){ result: internalId(typeidId: $type_id, outerId: $outer_id) }'
        jsonData = await self.queryGQL3(query=query, variables={"outer_id": outer_id, "type_id": type_id})
        data = jsonData.get("data", {"result": None})
        result = data.get("result", None)
        return result
   
    @alru_cache()
    async def getAllTypes(self):
        query = self.GetQuery(tableName="externalidtypes", queryType="readp")
        jsonData = await self.queryGQL3(query=query, variables={"limit": 1000})
        data = jsonData.get("data", {"result": None})
        result = data.get("result", None)
        assert result is not None, f"unable to get externalidtypes"
        asdict = {item["name"]: item["id"] for item in result}
        return asdict
 
    @alru_cache(maxsize=1024)
    async def getTypeId(self, typeName):
        """podle typeName zjisti typeID
           cte pomoci query na gql endpointu
        """
        alltypes = await self.getAllTypes()
        result = alltypes.get(typeName, None)
        assert result is not None, f"unable to get id of type {typeName}"
        return result
 
    async def registerID(self, inner_id, outer_id, type_id):
        # assert inner_id is not None, f"missing {inner_id} in registerID"
        # assert outer_id is not None, f"missing {outer_id} in registerID"
        # assert type_id is not None, f"missing {type_id} in registerID"
 
        "zaregistruje vnitrni hodnotu primarniho klice (inner_id) a zpristupni jej pres puvodni id (outer_id a type_id)"
        mutation = '''
            mutation ($type_id: UUID!, $inner_id: UUID!, $outer_id: String!) {
                result: externalidInsert(
                    externalid: {innerId: $inner_id, typeidId: $type_id, outerId: $outer_id}
                ) {
                    msg
                    result: externalid {
                        id    
                        }
                    }
                }
        '''
        jsonData = await self.queryGQL3(query=mutation, variables={"inner_id": inner_id, "outer_id": outer_id, "type_id": type_id})
        data = jsonData.get("data", {"result": {"msg": "fail"}})
        msg = data["result"]["msg"]
        if msg != "ok":
            print(f'register ID failed ({ {"inner_id": inner_id, "outer_id": outer_id, "type_id": type_id} })\n\tprobably already registered')
        else:
            print(f"registered {outer_id} for {inner_id} ({type_id})")
        return "ok"
 
    async def Read(self, tableName, variables, outer_id=None, outer_id_type_id=None):
        if outer_id:
            # read external id
            assert outer_id_type_id is not None, f"if outer_id ({outer_id}) defined, outer_id_type_id must be defined also "
            inner_id = await self.asyncTranslateID(outer_id=outer_id, type_id=outer_id_type_id)
            assert inner_id is not None, f"outer_id {outer_id} od type_id {outer_id_type_id} mapping failed on table {tableName}"
            variables = {**variables, "id": inner_id}
 
        queryRead = self.GetQuery(tableName, "read")
        response = await self.queryGQL3(query=queryRead, variables=variables)
        error = response.get("errors", None)
        assert error is None, f"error {error} during query \n{queryRead}\n with variables {variables}".replace("'", '"')
        data = response.get("data", None)
        assert data is not None, f"got no data during query \n{queryRead}\n with variables {variables}".replace("'", '"')
        result = data.get("result", None)
        # assert result is not None, f"missint result in response \n{response}\nto query \n{queryRead}\n with variables {variables}".replace("'", '"')
        return result
   
    async def Create(self, tableName, variables, outer_id=None, outer_id_type_id=None):
        queryType = "create"
        if outer_id:
            # read external id
            assert outer_id_type_id is not None, f"if outer_id ({outer_id}) defined, outer_id_type_id must be defined also "
            inner_id = await self.asyncTranslateID(outer_id=outer_id, type_id=outer_id_type_id)
           
            if inner_id:
                print(f"outer_id ({outer_id}) defined ({outer_id_type_id}) \t on table {tableName},\t going update")
                old_data = await self.Read(tableName=tableName, variables={"id": inner_id})
                if old_data is None:
                    print(f"found corrupted data, entity with id {inner_id} in table {tableName} is missing, going to create it")
                    variables = {**variables, "id": inner_id}
                else:
                    variables = {**old_data, **variables, "id": inner_id}
                    queryType = "update"
            else:
                print(f"outer_id ({outer_id}) undefined ({outer_id_type_id}) \t on table {tableName},\t going insert")
                registrationResult = await self.registerID(
                    inner_id=variables["id"],
                    outer_id=outer_id,
                    type_id=outer_id_type_id
                    )
                assert registrationResult == "ok", f"Something is really bad, ID reagistration failed"
 
        query = self.GetQuery(tableName, queryType)
        assert query is not None, f"missing {queryType} query for table {tableName}"
        response = await self.queryGQL3(query=query, variables=variables)
        data = response["data"]
        result = data["result"] # operation result
        result = result["result"] # entity result
        return result
 
from bs4 import BeautifulSoup
rozvrhid="ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl00_LvApplicationsList_ctrl6_btnApp"
vavid="ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl01_LvApplicationsList_ctrl1_btnApp"
mojeapid="ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl1_ctl00_LvApplicationsList_ctrl4_btnApp"
dymado_id="ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl01_LvApplicationsList_ctrl0_btnApp"
 
class ScraperBase:
    def __init__(self,
        username,
        password,
        cacheFileName = "./pageindex.json",
        cachedir = "./pagecache/",
        app_id = mojeapid,
        writer = None
    ):
       
        # zajisti, ze adresar bude existovat
        Path(cachedir).mkdir(exist_ok=True)
 
        self.username = username
        self.password = password
        self.cacheFileName = cacheFileName
        self.cachedir = cachedir
        self.app_id = app_id
        self.timeout = 1000
        self.writer = writer
 
        with open(cacheFileName, "r", encoding="utf-8") as f:
            self.pageindex = json.load(f)
        pass
 
    def writeCache(self):
        "zapise data do json, prepise soubor kompletne"
        with open(self.cacheFileName, "w", encoding="utf-8") as f:
            json.dump(self.pageindex, f, indent=4)
 
    @cache
    def getDriver(self):
        "inicializuje driver"
        options = FirefoxOptions()
        options.set_preference('devtools.jsonview.enabled', False)
        driver = webdriver.Firefox(options=options)
 
        return driver
 
    @cache
    def login(self):
        "inicializuje driver, prihlasi uzivatele a driver vrati"
        #
        # username, password
        #
        driver = self.getDriver()
        driver.get("https://intranet.unob.cz/aplikace/SitePages/DomovskaStranka.aspx")
 
        elem = WebDriverWait(driver, 100).until(
                expected_conditions.presence_of_element_located((By.ID, "userNameInput"))
            )
 
        # elem = driver.find_element(By.ID, "userNameInput")
        elem.clear()
        elem.send_keys(self.username)
        elem.send_keys(Keys.RETURN)
 
        elem = driver.find_element(By.ID, "passwordInput")
        elem.clear()
        elem.send_keys(self.password)
        elem.send_keys(Keys.RETURN)
        return driver
 
    @cache
    def loginApp(self, app_id):
        driver = self.login()
        driver.get("https://intranet.unob.cz/aplikace/SitePages/DomovskaStranka.aspx")
 
        # toto ID si najdete a prizpusobte kod
        elem = WebDriverWait(driver, self.timeout).until(
                expected_conditions.presence_of_element_located((By.ID, app_id))
            )
        elem.click()
        return driver      
   
    def guessAppId(self, url):
        appids = {
                'https://vav.unob.cz/': "ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl01_LvApplicationsList_ctrl1_btnApp",
                'https://apl.unob.cz/MojeAP/': "ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl1_ctl00_LvApplicationsList_ctrl4_btnApp",
                'https://apl.unob.cz/Dymado/': "ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl01_LvApplicationsList_ctrl0_btnApp",
                "https://apl.unob.cz/Rozvrh/": "ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl00_LvApplicationsList_ctrl6_btnApp",
                "https://vav.unob.cz/": "ctl00_ctl40_g_ba0590ba_842f_4a3a_b2ea_0c665ea80655_ctl00_LvApplicationGroupList_ctrl0_ctl01_LvApplicationsList_ctrl1_btnApp"
            }
        best = ""
        bestvalue = -1
        for path, id in appids.items():
            similarity = 0
            for chara, charb in zip(path, url):
                if chara != charb:
                    break
                similarity += 1
            if bestvalue < similarity:
                bestvalue = similarity
                best = id
               
        return best
 
    def scrapepage(self, url):
        "ziska driver (pokud poprve, provede inicializaci), prihlasi se do aplikace (jestli neni jeste prihlasen), otevre page a vrati jeji obsah"
 
        appid = self.guessAppId(url)
        webdriver = self.loginApp(appid)
        # webdriver = self.openWeb()
 
        webdriver.get(url)            
        # mozna budete muset zmenit podminku, pokud zdroj vyuziva intenzivne javascript (kresli stranku na klientovi)
        # WebDriverWait(webdriver, self.timeout).until(
        #     expected_conditions.url_contains(url)
        # )
        result = webdriver.page_source
        return result
 
    def openUrl(self, url):
        """vytvari index stranek, aby se minimalizovala komunikace se serverem,
        stranky se ukladaji do adresare,
        pokud zdroj nema permalinky, ma tento pristup stinne stranky = stejna url maji jiny obsah
        index je ulozen jako json, keys jsou urls, values jsou uuids = nazvy souboru, kde jsou stranky ulozeny
        """
        pageid = self.pageindex.get(url, None)
        result = ""
        if pageid:
            filename = self.cachedir + pageid + ".html"
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
                result = "\n".join(lines)
        else:
            pageid = f"{uuid4()}"
            filename = self.cachedir + pageid + ".html"
            self.pageindex[url] = pageid
            result = self.scrapepage(url)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(result)
            self.writeCache()
 
        return result
   
class Analyzer:
    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password
        self.writer = DBWriter() # using default user
        self.scraper = ScraperBase(self.username, self.password)
       
    async def gatherPage(self, url, method):
        pageContent = self.scraper.openUrl(url)
        await method(pageContent)
 
    async def events(self, pageContent):
        "z rozvrhu extrahuje udalosti"
        eventtypes = {
            "Ostatní": "b87d3ff0-8fd4-11ed-a6d4-0242ac110002",
            "LAB": "b87d7b28-8fd4-11ed-a6d4-0242ac110002",
            "P": "b87d7be6-8fd4-11ed-a6d4-0242ac110002",
            "CV": "b87d7c2c-8fd4-11ed-a6d4-0242ac110002",
            "SEM": "b87d7ce0-8fd4-11ed-a6d4-0242ac110002",
            "PV": "b87d7eb6-8fd4-11ed-a6d4-0242ac110002",
            "ZK": "b87d82e4-8fd4-11ed-a6d4-0242ac110002",
            "EX": "b87d8442-8fd4-11ed-a6d4-0242ac110002",
            "STŽ": "b87d90e0-8fd4-11ed-a6d4-0242ac110002",
            "KON": "b87d9266-8fd4-11ed-a6d4-0242ac110002",
            "PX": "b87d9400-8fd4-11ed-a6d4-0242ac110002",
            "TER": "b87d98c4-8fd4-11ed-a6d4-0242ac110002",
            "KRZ": "b87e1010-8fd4-11ed-a6d4-0242ac110002",
            "J": "b87e5796-8fd4-11ed-a6d4-0242ac110002",
            "SMP": "b87e6380-8fd4-11ed-a6d4-0242ac110002",
            "KOL": "b87e69b6-8fd4-11ed-a6d4-0242ac110002",
            "SPK": "b87e6c04-8fd4-11ed-a6d4-0242ac110002",
            "SZK": "b87f7cac-8fd4-11ed-a6d4-0242ac110002",
            "SMS": "b8803df4-8fd4-11ed-a6d4-0242ac110002",
        }
        jsonData = json.loads(pageContent)
        events = jsonData["events"]
        awaitables = []
        for event in events:
            outer_id = event["id"]
            startdate = f'{event["dateCode"]}T{str(event["startTime"]["hours"]).zfill(2)}:{str(event["startTime"]["minutes"]).zfill(2)}:00'
            enddate = f'{event["dateCode"]}T{str(event["endTime"]["hours"]).zfill(2)}:{str(event["endTime"]["minutes"]).zfill(2)}:00'
            name = event.get("topic", event.get("subjectName", "Neuvedeno"))
            type_id = eventtypes.get(event.get("lessonFormName", "Ostatní"), "b87d3ff0-8fd4-11ed-a6d4-0242ac110002")
            event_entity = { "id": outer_id, "name": name, "startdate": startdate, "enddate": enddate, "type_id": type_id }
            awaitables.append(self.writer.Create("events", variables=event_entity, outer_id=outer_id, outer_id_type_id="0c37b3e1-a937-4776-9543-37ae846411de"))
            if len(awaitables) > 9:
                await asyncio.gather(*awaitables)
                awaitables = []
        await asyncio.gather(*awaitables)
        return "ok"
 
 
password = ""
password = getpass.getpass()
 
username = "who@where.com"
username = "some.body@domain.com"
# gatherVvi(username, password)
# gatherDymado(username, password)
async def gatherAsync(username, password):
 
   
    analyser = Analyzer(username=username, password=password)
 
    # dy_users_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/dymado/odata/UnobDbUser/",
    #     method=analyser.dy_users
    #     )
    # dy_groups_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/dymado/odata/UnobDbUserGroup/",
    #     method=analyser.dy_groups
    #     )
    # await asyncio.gather(dy_users_awaitable, dy_groups_awaitable)
 
    # dy_membership_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/dymado/odata/UnobDbUser_UserGroup/",
    #     method=analyser.dy_membership
    #     )
    events_awaitable = analyser.gatherPage(
        url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
        method=analyser.events
        )
    await events_awaitable
    # await asyncio.gather(dy_membership_awaitable, events_awaitable)
 
    # events_teachers_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method=analyser.events_teachers
    #     )
    # await asyncio.gather(events_teachers_awaitable)
 
    # events_student_groups_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method=analyser.event_student_groups
    # )
    # await asyncio.gather(events_student_groups_awaitable)
 
    # events_students_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method=analyser.event_students
    # )
    # await asyncio.gather(events_students_awaitable)
 
    # vav_users_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method=analyser.vav_users
    # )
    # await asyncio.gather(vav_users_awaitable)
 
    # events_program_awaitable = analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method= analyser.event_teachers_programs
    # )
    # await asyncio.gather(events_program_awaitable)
 
    # await analyser.gatherPage(
    #     url="https://apl.unob.cz/rozvrh/api/read/rozvrh?id=9",
    #     method=analyser.facilities_areals
    #     )
 
    # await analyser.gatherPage(
    #     url="https://apl.unob.cz/MojeAP/",
    #     method=analyser.ma_groups_structure
    #     )
 
    await analyser.gatherPage(
        url="https://vav.unob.cz/persons/index",
        method=analyser.vav_users_projects
    )    
    pass
 
asyncio.run(gatherAsync(username=username, password=password))