#!/usr/bin/env python3


import json
from pprint import pprint
import argh
from argh.assembling import set_default_command
import re
import requests
from requests.exceptions import HTTPError

__author__ = 'crystal'


class JiraConnection:
    template = 'https://{host}:{port}/rest/{api}/latest/{action}'

    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self.session = requests.session()

    def login(self):
        resp = self.make_request(
            action='session',
            json_body={
                'username': self.user,
                'password': self.password,
            },
            apiname='auth',
            verb='POST'
        )
        return resp.json()

    def get_issue_info(self, issue_key, expand='all'):
        resp = self.make_request(
            action='issue/' + issue_key,
            params={'expand': expand}
        )
        return resp.json()

    def make_request(self, action, params=None, json_body=None, verb='GET', apiname='api', ):
        try:
            url = self.template.format(action=action, api=apiname, **self.__dict__)
            print(url)
            resp = self.session.request(
                verb,
                url=url,
                params=params,
                json=json_body,
                verify=False,
                headers={
                    'Content-Type': 'application/json'
                },
                cookies=self.session.cookies
            )
            if str(resp.status_code).startswith('4') :
                raise HTTPError(resp.status_code)
        except HTTPError as e:
            print('%s occurred while processing %s ' % (e, action))
            raise
        return resp


@argh.arg('--host', default='jira.findmeals.ru')
@argh.arg('--port', default=443)
@argh.arg('--user')
@argh.arg('--password')
@argh.arg('commit_msg_file')
def main(args):
    connobj = JiraConnection(args.host, args.port, args.user, args.password)
    connobj.login()

    resp = connobj.make_request(action='field').json()
    epic_link_field_id = ([x['id'] for x in resp if x['name'] == 'Epic Link'] or [None])[0]

    def replace_func(orig_text, matchobj):
        key = matchobj.group(1)
        try:
            info = connobj.get_issue_info(key)
        except HTTPError:
            return 'refs #%s' % key
        else:
            if info['fields']['summary'] in orig_text:
                return 'refs #%s' % key
            else:
                summary = info['fields']['summary']
                components = ''
                if info['fields'].get('components'):
                    components = ' Компоненты: ' + '/'.join(
                        [x['name'] for x in info['fields']['components']]
                    )

                if 'parent' in info['fields']:
                    summary = info['fields']['parent']['fields']['summary'] + ' - ' + summary

                if epic_link_field_id and info['fields'].get(epic_link_field_id):
                    epic_summary = connobj.get_issue_info(info['fields'][epic_link_field_id])['fields']['summary']
                    summary = epic_summary + ' - ' + summary

                return 'refs #%s (%s)%s' % (
                    key,
                    summary,
                    components
                )

    with open(args.commit_msg_file, 'r+') as f:
        text = ''.join(f.readlines())
        f.seek(0)
        f.truncate()
        text = re.sub(r'refs\s*#(\w+-\d+)', lambda x: replace_func(text, x), text)
        f.write(text)


if __name__ == '__main__':
    parser = argh.ArghParser()
    set_default_command(parser, main)
    parser.dispatch()

