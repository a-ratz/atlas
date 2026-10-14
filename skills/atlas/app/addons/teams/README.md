# Teams addon

Microsoft Teams chats and channels in Atlas: a page in the navigation where you read and write
your chats, see the teams you are in, read their channels and post to them. A proof of concept:
text messages only. Calls, meetings, files and reactions stay in Teams.

## What it does with your data

- You sign in with your own Microsoft account. Atlas asks for **delegated** permissions only: it can
  do what you can do, nothing across your organization, and it has no client secret.
- The token is kept in `~/.atlas/addons/teams/token.json`, readable by you only, outside every vault.
  **Sign out** on the Teams page deletes it.
- Messages go from Microsoft Graph to your browser and nowhere else. They never land in the vault, in
  git, in the index or in your agent's chat, and your agents are told not to read them
  (`AGENTS.md`, rule 9).
- Messages are shown as text, never as HTML.
- New messages show up within seconds: Atlas asks Graph every few seconds for the open conversation
  and every half minute for the lists, and slows down when Graph says so.

## Try it with made-up people

```yaml
# <vault>/atlas.yaml
addons:
  teams:
    demo: true
```

Restart Atlas and open **Teams** in the navigation. The demo needs no account and no network.

## Connect your own Teams

You need an app registration in Microsoft Entra ID. If your organization does not let users register
apps, ask your admin to do these steps.

1. In the [Microsoft Entra admin center](https://entra.microsoft.com), open **App registrations** and
   choose **New registration**. Name it, for example, *Atlas*. Supported account types: *Accounts in
   this organizational directory only*.
2. Under **Authentication**, add the platform **Mobile and desktop applications** with the redirect URI
   `http://localhost/api/addons/teams/callback`. Atlas sends you back to
   `http://localhost:<port>/api/addons/teams/callback`; Entra ignores the port for `http://localhost`,
   but not the path. Open Atlas at `localhost`, not `127.0.0.1`.
3. Under **API permissions**, add these **delegated** Microsoft Graph permissions:

   | Permission | For | Admin consent |
   |---|---|---|
   | `User.Read`, `offline_access`, `openid`, `profile` | signing in and staying signed in | usually not needed |
   | `Chat.Read`, `ChatMessage.Send` | reading and writing your chats | usually not needed |
   | `Team.ReadBasic.All`, `Channel.ReadBasic.All` | the teams you are in and their channels | usually not needed |
   | `ChannelMessage.Send` | posting to a channel | usually not needed |
   | `ChannelMessage.Read.All` | reading channel posts | **always needed** |

   Your organization may require an admin's consent for all of them.
4. Copy the **Application (client) ID** and the **Directory (tenant) ID** from the overview into your
   vault's `atlas.yaml`:

   ```yaml
   addons:
     teams:
       client_id: <Application (client) ID>
       tenant: <Directory (tenant) ID>
       channel_messages: true   # only once an admin consented to ChannelMessage.Read.All
   ```

5. Restart Atlas, open **Teams** and choose **Sign in with Microsoft**.

Without `channel_messages: true` you can still post to a channel; the page says what is missing to
read it. Chats work either way.

## Not yet

Calls and meetings (join them in Teams), files, reactions, editing and deleting messages, attachments
(shown as a link to Teams), notifications outside the browser, older messages beyond the latest 50,
and reaching Atlas over the tailnet for signing in (the redirect needs `localhost`).
