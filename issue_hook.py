#!/usr/bin/env python3


import json
from pprint import pprint
import argh
from argh.assembling import set_default_command
import re
import requests
import sys
import os
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

    def get_user_by_email(self, email, expand='all'):
        resp = self.make_request(
            action='user/search',
            params={'username': email}
        )
        return resp.json()

    def create_issue(self, project_key, summary, description, issue_type, components, expand='all'):
        author = self.get_user_by_email(
            os.getenv('GIT_AUTHOR_EMAIL')
        )[0]['name']

        resp = self.make_request(
            action='issue/',
            params={'expand': expand},
            json_body={
                'fields': {
                    'project': {
                        'key': project_key
                    },
                    'issuetype': {
                        'id': issue_type
                    },
                    "assignee": {
                        "name": author
                    },
                    "reporter": {
                        "name": author
                    },
                    'summary': summary,
                    'description': description,
                    'components': [
                        {'id': id_}
                        for id_ in components
                    ]
                }
            },
            verb='POST'
        )
        return resp.json()

    def get_project_components(self, project_key, expand='all'):
        resp = self.make_request(
            action='project/%s/components' % project_key,
            params={'expand': expand}
        )
        return resp.json()

    def get_issue_types(self, expand='all'):
        resp = self.make_request(
            action='issuetype',
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
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/plain;q=0.7',  # Show errors in plain text or json, not XML
                },
                cookies=self.session.cookies
            )
            if str(resp.status_code).startswith('4') :
                print(resp.text)
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

    def create_issue(matchobj, orig_text, regexp):
        project_key = matchobj.group('project')

        issue_type_name = (re.findall(r'#(bug|feature)', orig_text.lower()) + ['bug'])[0]
        issue_type = [
            issue_type['id'] for issue_type
            in connobj.get_issue_types()
            if issue_type_name in issue_type['name'].lower()
        ][0]

        if '\n\n' in orig_text:
            summary, description = orig_text.split('\n\n', maxsplit=1)
        else:
            summary, description = orig_text, ''
        summary = regexp.sub('', summary)  # Header text without control tokens
        summary = re.sub(r'#(bug|feature)', '', summary)

        components_list = sorted(
            connobj.get_project_components(project_key),
            key=lambda x: x['name']
        )

        print('Enter one of the components below:')
        for idx, component in enumerate(components_list):
            print('%d. %s' % (idx, component['name']))
        component_idx = int(sys.stdin.readline())
        components = ' Компоненты: ' + components_list[component_idx]['name']



        result = connobj.create_issue(
            project_key,
            summary,
            description,
            issue_type,
            components=[components_list[component_idx]['id']]
        )
        print('Ссылка: %s' % result['self'])
        return 'refs #%s (%s)%s' % (result['key'], summary, components)

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
        text = ''.join(f.readlines()).strip()
        f.seek(0)
        f.truncate()

        regexp = re.compile(r'\s*refs #newissue\s+(?P<project>\w+)(?P<parent>-\d+)?\s*')
        matchobj = regexp.search(text)
        if matchobj:
            text = create_issue(matchobj, text, regexp=regexp)

        else:
            text = re.sub(text, lambda x: replace_func(text, x), text)
        f.write(text+'\n')


if __name__ == '__main__':
    parser = argh.ArghParser()
    set_default_command(parser, main)
    parser.dispatch()

