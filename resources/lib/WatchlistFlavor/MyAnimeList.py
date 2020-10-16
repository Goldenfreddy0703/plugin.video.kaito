import re
import bs4 as bs
import itertools
import json
import time
import requests
from WatchlistFlavorBase import WatchlistFlavorBase

class MyAnimeListWLF(WatchlistFlavorBase):
    _URL = "https://api.myanimelist.net/v2"
    _TITLE = "MyAnimeList"
    _NAME = "mal"
    _IMAGE = "https://cdn.myanimelist.net/images/mal-logo-xsmall@2x.png?v=160803001"

    def login(self):
        try:
            import urlparse
            parsed = urlparse.urlparse(self._auth_var)
            params = urlparse.parse_qs(parsed.query)
            code = params['code']
            code_verifier = params['state']
        except:
            return
        
        oauth_url = 'https://myanimelist.net/v1/oauth2/token'
        data = {
            'client_id': 'a8d85a4106b259b8c9470011ce2f76bc',
            'code': code,
            'code_verifier': code_verifier,
            'grant_type': 'authorization_code'
            }
        res = requests.post(oauth_url, data=data).json()

        self._token = res['access_token']
        user = requests.get('https://api.myanimelist.net/v2/users/@me?fields=name', headers=self.__headers()).json()

        login_data = {
            'token': res['access_token'],
            'refresh': res['refresh_token'],
            'expiry': str(time.time() + int(res['expires_in'])),
            'username': user['name']
            }

        return login_data

    def refresh_token(self, control):
        oauth_url = 'https://myanimelist.net/v1/oauth2/token'
        data = {
            'client_id': 'a8d85a4106b259b8c9470011ce2f76bc',
            'grant_type': 'refresh_token',
            'refresh_token': control.getSetting('mal.refresh')
            }
        res = requests.post(oauth_url, data=data).json()
        control.setSetting('mal.token', res['access_token'])
        control.setSetting('mal.refresh', res['refresh_token'])
        control.setSetting('mal.expiry', str(time.time() + int(res['expires_in'])))

    def _handle_paging(self, hasNextPage, base_url, page):
        if not hasNextPage:
            return []

        next_page = page + 1
        name = "Next Page (%d)" %(next_page)
        offset = (re.compile("offset=(.+?)&").findall(hasNextPage))[0]
        return self._parse_view({'name':name, 'url': base_url % (offset, next_page), 'image': None, 'plot': None})

    def watchlist(self):
        return self._process_watchlist_view('', "watchlist_page/%d", page=1)

    def _base_watchlist_view(self, res):
        base = {
            "name": res[0],
            "url": 'watchlist_status_type/%s/%s' % (self._NAME, res[1]),
            "image": '',
            "plot": '',
        }

        return self._parse_view(base)

    def _process_watchlist_view(self, params, base_plugin_url, page):
        all_results = map(self._base_watchlist_view, self.__mal_statuses())
        all_results = list(itertools.chain(*all_results))
        return all_results

    def __mal_statuses(self):
        statuses = [
            ("Currently Watching", "watching"),
            ("Completed", "completed"),
            ("On Hold", "on_hold"),
            ("Dropped", "dropped"),
            ("Plan to Watch", "plan_to_watch"),
            ("All Anime", ""),
            ]

        return statuses
        
    def get_watchlist_status(self, status, offset=0, page=1):
        params = {
            "status": status,
            "order": self.__get_sort(),
            "limit": 100,
            "offset": offset,
            "fields": 'list_status,num_episodes,synopsis,media_type,average_episode_duration',
            }

        url = self._to_url("users/@me/animelist")
        return self._process_status_view(url, params, "watchlist_status_type_pages/mal/%s/%%s/%%d" % status, page)

    def _process_status_view(self, url, params, base_plugin_url, page):
        results = (self._get_request(url, headers=self.__headers(), params=params)).json()
        all_results = map(self._base_watchlist_status_view, results['data'])
        all_results = list(itertools.chain(*all_results))

        all_results += self._handle_paging(results['paging'].get('next'), base_plugin_url, page)
        return all_results

    def _base_watchlist_status_view(self, res):
        info = {}

        try:
            info['plot'] = res['node']['synopsis']
        except:
            pass

        try:
            info['duration'] = res['node']['average_episode_duration']
        except:
            pass
        

        base = {
            "name": '%s - %s/%s' % (res['node']["title"], res['list_status']["num_episodes_watched"], res['node']["num_episodes"]),
            "url": "watchlist_to_ep/%s//%s" % (res['node']['id'], res['list_status']["num_episodes_watched"]),
            "image": res['node']['main_picture'].get('large', res['node']['main_picture']['medium']),
            "plot": info,
        }

        if res['node']['media_type'] == 'movie' and res['node']["num_episodes"] == 1:
            base['url'] = "watchlist_to_movie/%s" % (res['node']['id'])
            base['plot']['mediatype'] = 'movie'
            return self._parse_view(base, False)

        return self._parse_view(base)

    def __headers(self):
        header = {
            'Authorization': "Bearer {}".format(self._token),
            'Content-Type': 'application/x-www-form-urlencoded'
            }

        return header

    def _kitsu_to_mal_id(self, kitsu_id):
        arm_resp = self._get_request("https://arm.now.sh/api/v1/search?type=kitsu&id=" + kitsu_id)
        if arm_resp.status_code != 200:
            raise Exception("AnimeID not found")

        mal_id = arm_resp.json()["services"]["mal"]
        return mal_id

    def watchlist_update(self, anilist_id, episode):
        mal_id = self._get_mapping_id(anilist_id, 'mal_id')

        if not mal_id:
            return

        url = self._to_url("anime/%s/my_list_status" % (mal_id))
        data = {
            'num_watched_episodes': int(episode)
            }

        return lambda: self.__update_watchlist(anilist_id, episode, url, data)

    def __update_watchlist(self, anilist_id, episode, url, data):
        r = requests.put(url, data=data, headers=self.__headers())

    def __get_sort(self):
        sort_types = {
            "Anime Title": "anime_title",
            "Last Updated": "list_updated_at",
            "Anime Start Date": "anime_start_date",
            "List Score": "list_score"
            }

        return sort_types[self._sort]