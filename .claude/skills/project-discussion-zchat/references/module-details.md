# zchat Module Details Reference

> Auto-generated from module analysis. JSON reports at `.artifacts/bootstrap/module-reports/`.

## Module Dependency Graph

```
app (CLI entry)
  +-- project        (create/list/use/remove/resolve)
  +-- agent_manager   (create/stop/restart/list/send)
  |     +-- zellij        (tab lifecycle)
  |     +-- irc_manager   (connectivity check)
  |     +-- runner         (env rendering, template resolution)
  |     +-- auth           (credentials, username)
  +-- irc_manager     (ergo daemon, WeeChat)
  |     +-- zellij
  |     +-- auth
  +-- config_cmd      (global config)
  |     +-- defaults
  +-- update          (version check, upgrade)
  +-- layout          (KDL generation)
  +-- template_loader (template discovery)
  +-- doctor          (diagnostics)

paths      <-- used by: project, auth, config_cmd, runner, template_loader, layout, update, app
defaults   <-- used by: project, config_cmd, paths, app
zellij     <-- used by: agent_manager, irc_manager, layout, app (no deps itself)
migrate    <-- standalone (no deps, no dependents in normal flow)
```

## Module Summary Table

| Module | File | Key Responsibility | Tests |
|--------|------|--------------------|-------|
| agent_manager | `zchat/cli/agent_manager.py` | Agent lifecycle: create workspace, spawn zellij tab, track state | 19/19 |
| irc_manager | `zchat/cli/irc_manager.py` | Ergo IRC daemon + WeeChat management | 3/4 (1 WSL2) |
| auth | `zchat/cli/auth.py` | OIDC device code flow, token cache, credentials | 15/15 |
| ergo_auth_script | `zchat/cli/ergo_auth_script.py` | Ergo SASL auth-script (Keycloak userinfo validation) | 4/4 |
| project | `zchat/cli/project.py` | Project CRUD, config.toml, resolve project | 22/22 |
| layout | `zchat/cli/layout.py` | KDL layout generation for Zellij sessions | 8/8 |
| zellij | `zchat/cli/zellij.py` | Thin Zellij CLI helpers (session, tab, pane ops) | 22/22 |
| config_cmd | `zchat/cli/config_cmd.py` | Global config (~/.zchat/config.toml), server resolution | 11/11 |
| defaults | `zchat/cli/defaults.py` | Built-in defaults from data/defaults.toml | 6/6 |
| paths | `zchat/cli/paths.py` | Centralized path resolution (env > config > defaults) | 24/24 |
| runner | `zchat/cli/runner.py` | Runner resolution: merge global config + template assets | 16/16 |
| template_loader | `zchat/cli/template_loader.py` | Template discovery, loading, env rendering | 8/8 |
| migrate | `zchat/cli/migrate.py` | Config/state migration from tmux to Zellij format | 4/4 |
| update | `zchat/cli/update.py` | Update checking (git/PyPI) and atomic upgrade | 19/19 |
| doctor | `zchat/cli/doctor.py` | Environment diagnostics, weechat plugin setup | no tests |
| app | `zchat/cli/app.py` | Main Typer CLI app, command tree, session management | 11/11 |

**Total: 192 passed, 1 failed (WSL2 env), 0 skipped**

## Key Interfaces by Category

### Agent Lifecycle
- `AgentManager.create(name, workspace, channels, agent_type)` -- agent_manager.py:65
- `AgentManager.stop(name, force)` -- agent_manager.py:100
- `AgentManager.restart(name)` -- agent_manager.py:113
- `AgentManager.list_agents()` -- agent_manager.py:124
- `AgentManager.send(name, text)` -- agent_manager.py:332

### IRC Management
- `check_irc_connectivity(server, port, tls, timeout)` -- irc_manager.py:13
- `IrcManager.daemon_start(port_override)` -- irc_manager.py:40
- `IrcManager.daemon_stop()` -- irc_manager.py:168
- `IrcManager.start_weechat(nick_override)` -- irc_manager.py:183
- `IrcManager.build_weechat_cmd(nick_override)` -- irc_manager.py:208

### Authentication
- `get_username(base_dir)` -- auth.py:20
- `get_credentials(base_dir, client_id, http_client)` -- auth.py:238
- `device_code_flow(issuer, client_id, http_client)` -- auth.py:137
- `save_token(base_dir, token_data)` -- auth.py:49
- `validate_credentials(account_name, passphrase, userinfo_url)` -- ergo_auth_script.py:25

### Project Management
- `create_project_config(name, server, nick, channels, ...)` -- project.py:24
- `load_project_config(name)` -- project.py:94
- `resolve_project(explicit)` -- project.py:81
- `list_projects()` -- project.py:62
- `remove_project(name)` -- project.py:123

### Configuration
- `load_global_config(path)` -- config_cmd.py:19
- `resolve_server(server_ref, global_config)` -- config_cmd.py:41
- `load_defaults()` -- defaults.py:11

### Path Resolution
- `zchat_home()` -- paths.py:14
- `project_dir(name)` -- paths.py:103
- `plugins_dir()` -- paths.py:59
- `templates_dir()` -- paths.py:64

### Zellij Operations
- `ensure_session(name, layout, config)` -- zellij.py:26
- `new_tab(session, name, command, cwd)` -- zellij.py:75
- `close_tab(session, tab_name)` -- zellij.py:86
- `send_command(session, pane_id, text)` -- zellij.py:124
- `tab_exists(session, tab_name)` -- zellij.py:153

### Templates & Runners
- `resolve_runner(name, global_config, user_template_dirs)` -- runner.py:75
- `render_env(template_dir_or_name, context)` -- runner.py:144
- `resolve_template_dir(name)` -- template_loader.py:18
- `list_templates()` -- template_loader.py:85

### Layout
- `generate_layout(config, state, weechat_cmd, project_name)` -- layout.py:19
- `write_layout(project_dir, config, state, weechat_cmd, project_name)` -- layout.py:86

### Update
- `check_for_updates(state)` -- update.py:87
- `run_upgrade(channel)` -- update.py:134
- `should_check_today(state)` -- update.py:48

### Migration
- `migrate_config_if_needed(project_dir)` -- migrate.py:12
- `migrate_state_if_needed(project_dir)` -- migrate.py:59
