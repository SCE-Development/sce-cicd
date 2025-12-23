# sce's cicd server

### how to run
- [ ] get the smee url and discord webhook url from a dev member
- [ ] create a `.env` file like
```
SMEE_URL=https://smee.io/SOME_VALUE_HERE
CICD_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REST_OF_VALUE_HERE
```
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
- [ ] (if not development) create a `config.yml` file like
```yml
repos:
  - name: git-workshop
    branch: main
    path: /home/sce/git-workshop
  - name: monitoring
    branch: main
    path: /home/sce/monitoring
```
- [ ] in the same terminal, run the server with
```sh
python server.py --development
```

### for development
- [ ] follow the above steps to setup + the server
- [ ] push small, random commits directly to https://github.com/SCE-Development/git-workshop
- [ ] ensure that the embeds + logs as a result of the above activity


### faq
#### why `"smee-client": "2.0.0"`?
Some machines that we run this on do not have GLIBC_2.28, i.e.
```sh
# npx smee
node: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.28' not found (required by node)
```
version 2.0.0 allows us to use node 16.

#### how do i install python3.10 from source?
```sh
wget https://www.python.org/ftp/python/3.10.4/Python-3.10.4.tgz

tar -xvf Python-3.10.4.tgz

cd Python-3.10.4

# Configure for /usr/local (keeps it separate from system python3.6)
./configure --enable-optimizations

# Build with multiple cores (adjust -j to your CPU count)
make -j$(nproc)

# Install *alongside* system python, don't overwrite
sudo make altinstall

# you should now be able to run python3.10 without issue
python3.10
```
#### why install node-fetch?
to get around this error
```
TypeError: this.fetch is not a function
    at Client.onmessage (/path/to/sce-cicd/node_modules/smee-client/index.js:44:41)
    at EventSource.emit (events.js:314:20)
    at _emit (/path/to/sce-cicd/node_modules/eventsource/lib/eventsource.js:287:17)
    at parseEventStreamLine (/path/to/sce-cicd/node_modules/eventsource/lib/eventsource.js:302:9)
    at IncomingMessage.<anonymous> (/path/to/sce-cicd/node_modules/eventsource/lib/eventsource.js:259:11)
    at IncomingMessage.emit (events.js:314:20)
    at addChunk (_stream_readable.js:304:12)
    at readableAddChunk (_stream_readable.js:280:9)
    at IncomingMessage.Readable.push (_stream_readable.js:219:10)
    at HTTPParser.parserOnBody (_http_common.js:132:24)
```
#### applying smee-fetch.patch?
```sh
# after npm install, assuming ur on the real machine
patch /home/sce/sce-cicd/node_modules/smee-client/index.js < smee-fetch.patch
```
#### testing without pushing a commit?
you can use curl, for example
```sh
curl -X POST SMEE_URL_GOES_HERE \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{
        "ref": "refs/heads/main",
        "repository": {
          "name": "git-workshop"
        }
      }'
```


### example webhook json
```json
{
    "ref": "refs/heads/deubgzone",
    "before": "0000000000000000000000000000000000000000",
    "after": "ff14e09013a054660b42cdb73d4cb1eb492d3e54",
    "repository": {
        "id": 698141681,
        "node_id": "R_kgDOKZzL8Q",
        "name": "git-workshop",
        "full_name": "SCE-Development/git-workshop",
        "private": false,
        "owner": {
            "name": "SCE-Development",
            "email": null,
            "login": "SCE-Development",
            "id": 17789654,
            "node_id": "MDEyOk9yZ2FuaXphdGlvbjE3Nzg5NjU0",
            "avatar_url": "https://avatars.githubusercontent.com/u/17789654?v=4",
            "gravatar_id": "",
            "url": "https://api.github.com/users/SCE-Development",
            "html_url": "https://github.com/SCE-Development",
            "followers_url": "https://api.github.com/users/SCE-Development/followers",
            "following_url": "https://api.github.com/users/SCE-Development/following{/other_user}",
            "gists_url": "https://api.github.com/users/SCE-Development/gists{/gist_id}",
            "starred_url": "https://api.github.com/users/SCE-Development/starred{/owner}{/repo}",
            "subscriptions_url": "https://api.github.com/users/SCE-Development/subscriptions",
            "organizations_url": "https://api.github.com/users/SCE-Development/orgs",
            "repos_url": "https://api.github.com/users/SCE-Development/repos",
            "events_url": "https://api.github.com/users/SCE-Development/events{/privacy}",
            "received_events_url": "https://api.github.com/users/SCE-Development/received_events",
            "type": "Organization",
            "user_view_type": "public",
            "site_admin": false
        },
        "html_url": "https://github.com/SCE-Development/git-workshop",
        "description": "The second part of the interview to join the SCE Internship",
        "fork": false,
        "url": "https://api.github.com/repos/SCE-Development/git-workshop",
        "forks_url": "https://api.github.com/repos/SCE-Development/git-workshop/forks",
        "keys_url": "https://api.github.com/repos/SCE-Development/git-workshop/keys{/key_id}",
        "collaborators_url": "https://api.github.com/repos/SCE-Development/git-workshop/collaborators{/collaborator}",
        "teams_url": "https://api.github.com/repos/SCE-Development/git-workshop/teams",
        "hooks_url": "https://api.github.com/repos/SCE-Development/git-workshop/hooks",
        "issue_events_url": "https://api.github.com/repos/SCE-Development/git-workshop/issues/events{/number}",
        "events_url": "https://api.github.com/repos/SCE-Development/git-workshop/events",
        "assignees_url": "https://api.github.com/repos/SCE-Development/git-workshop/assignees{/user}",
        "branches_url": "https://api.github.com/repos/SCE-Development/git-workshop/branches{/branch}",
        "tags_url": "https://api.github.com/repos/SCE-Development/git-workshop/tags",
        "blobs_url": "https://api.github.com/repos/SCE-Development/git-workshop/git/blobs{/sha}",
        "git_tags_url": "https://api.github.com/repos/SCE-Development/git-workshop/git/tags{/sha}",
        "git_refs_url": "https://api.github.com/repos/SCE-Development/git-workshop/git/refs{/sha}",
        "trees_url": "https://api.github.com/repos/SCE-Development/git-workshop/git/trees{/sha}",
        "statuses_url": "https://api.github.com/repos/SCE-Development/git-workshop/statuses/{sha}",
        "languages_url": "https://api.github.com/repos/SCE-Development/git-workshop/languages",
        "stargazers_url": "https://api.github.com/repos/SCE-Development/git-workshop/stargazers",
        "contributors_url": "https://api.github.com/repos/SCE-Development/git-workshop/contributors",
        "subscribers_url": "https://api.github.com/repos/SCE-Development/git-workshop/subscribers",
        "subscription_url": "https://api.github.com/repos/SCE-Development/git-workshop/subscription",
        "commits_url": "https://api.github.com/repos/SCE-Development/git-workshop/commits{/sha}",
        "git_commits_url": "https://api.github.com/repos/SCE-Development/git-workshop/git/commits{/sha}",
        "comments_url": "https://api.github.com/repos/SCE-Development/git-workshop/comments{/number}",
        "issue_comment_url": "https://api.github.com/repos/SCE-Development/git-workshop/issues/comments{/number}",
        "contents_url": "https://api.github.com/repos/SCE-Development/git-workshop/contents/{+path}",
        "compare_url": "https://api.github.com/repos/SCE-Development/git-workshop/compare/{base}...{head}",
        "merges_url": "https://api.github.com/repos/SCE-Development/git-workshop/merges",
        "archive_url": "https://api.github.com/repos/SCE-Development/git-workshop/{archive_format}{/ref}",
        "downloads_url": "https://api.github.com/repos/SCE-Development/git-workshop/downloads",
        "issues_url": "https://api.github.com/repos/SCE-Development/git-workshop/issues{/number}",
        "pulls_url": "https://api.github.com/repos/SCE-Development/git-workshop/pulls{/number}",
        "milestones_url": "https://api.github.com/repos/SCE-Development/git-workshop/milestones{/number}",
        "notifications_url": "https://api.github.com/repos/SCE-Development/git-workshop/notifications{?since,all,participating}",
        "labels_url": "https://api.github.com/repos/SCE-Development/git-workshop/labels{/name}",
        "releases_url": "https://api.github.com/repos/SCE-Development/git-workshop/releases{/id}",
        "deployments_url": "https://api.github.com/repos/SCE-Development/git-workshop/deployments",
        "created_at": 1695977466,
        "updated_at": "2025-12-23T20:32:18Z",
        "pushed_at": 1766526229,
        "git_url": "git://github.com/SCE-Development/git-workshop.git",
        "ssh_url": "git@github.com:SCE-Development/git-workshop.git",
        "clone_url": "https://github.com/SCE-Development/git-workshop.git",
        "svn_url": "https://github.com/SCE-Development/git-workshop",
        "homepage": "https://sce.sjsu.edu",
        "size": 302,
        "stargazers_count": 3,
        "watchers_count": 3,
        "language": "HTML",
        "has_issues": true,
        "has_projects": false,
        "has_downloads": true,
        "has_wiki": false,
        "has_pages": false,
        "has_discussions": false,
        "forks_count": 44,
        "mirror_url": null,
        "archived": false,
        "disabled": false,
        "open_issues_count": 4,
        "license": null,
        "allow_forking": true,
        "is_template": false,
        "web_commit_signoff_required": false,
        "topics": [],
        "visibility": "public",
        "forks": 44,
        "open_issues": 4,
        "watchers": 3,
        "default_branch": "main",
        "stargazers": 3,
        "master_branch": "main",
        "organization": "SCE-Development",
        "custom_properties": {}
    },
    "pusher": {
        "name": "USER_GOES_HERE",
        "email": "36345325+USER_GOES_HERE@users.noreply.github.com"
    },
    "organization": {
        "login": "SCE-Development",
        "id": 17789654,
        "node_id": "MDEyOk9yZ2FuaXphdGlvbjE3Nzg5NjU0",
        "url": "https://api.github.com/orgs/SCE-Development",
        "repos_url": "https://api.github.com/orgs/SCE-Development/repos",
        "events_url": "https://api.github.com/orgs/SCE-Development/events",
        "hooks_url": "https://api.github.com/orgs/SCE-Development/hooks",
        "issues_url": "https://api.github.com/orgs/SCE-Development/issues",
        "members_url": "https://api.github.com/orgs/SCE-Development/members{/member}",
        "public_members_url": "https://api.github.com/orgs/SCE-Development/public_members{/member}",
        "avatar_url": "https://avatars.githubusercontent.com/u/17789654?v=4",
        "description": ""
    },
    "sender": {
        "login": "USER_GOES_HERE",
        "id": 36345325,
        "node_id": "MDQ6VXNlcjM2MzQ1MzI1",
        "avatar_url": "https://avatars.githubusercontent.com/u/36345325?v=4",
        "gravatar_id": "",
        "url": "https://api.github.com/users/USER_GOES_HERE",
        "html_url": "https://github.com/USER_GOES_HERE",
        "followers_url": "https://api.github.com/users/USER_GOES_HERE/followers",
        "following_url": "https://api.github.com/users/USER_GOES_HERE/following{/other_user}",
        "gists_url": "https://api.github.com/users/USER_GOES_HERE/gists{/gist_id}",
        "starred_url": "https://api.github.com/users/USER_GOES_HERE/starred{/owner}{/repo}",
        "subscriptions_url": "https://api.github.com/users/USER_GOES_HERE/subscriptions",
        "organizations_url": "https://api.github.com/users/USER_GOES_HERE/orgs",
        "repos_url": "https://api.github.com/users/USER_GOES_HERE/repos",
        "events_url": "https://api.github.com/users/USER_GOES_HERE/events{/privacy}",
        "received_events_url": "https://api.github.com/users/USER_GOES_HERE/received_events",
        "type": "User",
        "user_view_type": "public",
        "site_admin": false
    },
    "created": true,
    "deleted": false,
    "forced": false,
    "base_ref": null,
    "compare": "https://github.com/SCE-Development/git-workshop/commit/ff14e09013a0",
    "commits": [
        {
            "id": "ff14e09013a054660b42cdb73d4cb1eb492d3e54",
            "tree_id": "7a09b73cc0c530d3953b55453ed2fe66fef392f2",
            "distinct": true,
            "message": "[cicd testing] empty commit",
            "timestamp": "2025-12-23T13:31:05-08:00",
            "url": "https://github.com/SCE-Development/git-workshop/commit/ff14e09013a054660b42cdb73d4cb1eb492d3e54",
            "author": {
                "name": "LOCAL_NAME_GOES_HERE",
                "email": "EMAIL_GOES_HERE",
                "date": "2025-12-23T13:31:05-08:00",
                "username": "USER_GOES_HERE"
            },
            "committer": {
                "name": "LOCAL_NAME_GOES_HERE",
                "email": "EMAIL_GOES_HERE",
                "date": "2025-12-23T13:31:05-08:00",
                "username": "USER_GOES_HERE"
            },
            "added": [],
            "removed": [],
            "modified": []
        }
    ],
    "head_commit": {
        "id": "ff14e09013a054660b42cdb73d4cb1eb492d3e54",
        "tree_id": "7a09b73cc0c530d3953b55453ed2fe66fef392f2",
        "distinct": true,
        "message": "[cicd testing] empty commit",
        "timestamp": "2025-12-23T13:31:05-08:00",
        "url": "https://github.com/SCE-Development/git-workshop/commit/ff14e09013a054660b42cdb73d4cb1eb492d3e54",
        "author": {
            "name": "LOCAL_NAME_GOES_HERE",
            "email": "EMAIL_GOES_HERE",
            "date": "2025-12-23T13:31:05-08:00",
            "username": "USER_GOES_HERE"
        },
        "committer": {
            "name": "LOCAL_NAME_GOES_HERE",
            "email": "EMAIL_GOES_HERE",
            "date": "2025-12-23T13:31:05-08:00",
            "username": "USER_GOES_HERE"
        },
        "added": [],
        "removed": [],
        "modified": []
    }
}

```
