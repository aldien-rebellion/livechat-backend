# Live Chat administration

Global administrators are explicit database privileges. New registrations start with
`is_admin=false`; sending an administrator flag or a different user ID from the
browser does not grant privileges. Authentication uses server-side sessions, and
authorization is checked again on every administrative request.

| Action | Global administrator | Workspace owner | Other member |
| --- | --- | --- | --- |
| Create workspace | Yes | No | No |
| Create channel in an active workspace | Yes | Yes | Yes |
| Delete workspace and its channel/message content | Yes | Own workspace | No |
| Delete channel and its message content | Yes | Own workspace | No |

A legacy workspace membership with role `admin` may also manage that workspace.
This does not grant global workspace creation privileges.

## Deployment and designated administrators

Run database migrations before serving this version. The backend deployment
workflow runs `alembic upgrade head`, then explicitly grants the following
registered Live Chat accounts:

```sh
docker compose exec -T backend python -m scripts.set_admin poorin.o@ku.th --grant
docker compose exec -T backend python -m scripts.set_admin aldienre@gmail.com --grant
```

These grants apply when the updated deployment workflow runs. They have not been
applied to the live database by preparing this change. Both accounts must already
exist; the command exits with an error if the email is not registered. Deployment
stops when a migration or grant fails.

For a manual grant or revocation, an operator with database/container access can run:

```sh
docker compose exec -T backend python -m scripts.set_admin person@example.com --grant
docker compose exec -T backend python -m scripts.set_admin person@example.com --revoke
```

Remove a designated account's grant command from the workflow before permanently
revoking it, or the next deployment will grant it again. Workspace owners are
determined by `workspaces.created_by`; their ownership is not changed by this CLI.

Existing browser sessions from the old, untracked-token version must sign in again
after deployment. After an operator changes an administrator flag, sign in again
to refresh the controls shown in the browser; the backend always reads the current
database privilege.

## Deletion behavior

The confirmation dialog identifies the selected resource and explains that its
message content is deleted. Deletion purges stored messages and leaves directory
tombstones so a stale browser or WebSocket cannot recreate the deleted room.
Directory refresh removes deleted resources from other users' lists. Deleted
names remain reserved.

Grafana administrator accounts are separate from Live Chat administrators. These
commands and privileges do not change Grafana login or administration settings.
