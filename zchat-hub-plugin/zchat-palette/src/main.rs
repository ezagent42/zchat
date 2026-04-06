use zellij_tile::prelude::*;
use serde::Deserialize;
use std::collections::{BTreeMap, VecDeque};

mod fuzzy;

/// System tab name suffixes that are not agents.
const SYSTEM_SUFFIXES: &[&str] = &["/chat", "/ctl"];

// ---------------------------------------------------------------------------
// Data types from `zchat list-commands` JSON
// ---------------------------------------------------------------------------

#[derive(Deserialize, Clone, Debug)]
struct CommandInfo {
    name: String,
    args: Vec<ArgInfo>,
}

#[derive(Deserialize, Clone, Debug)]
struct ArgInfo {
    name: String,
    required: bool,
    source: Option<String>,
}

// ---------------------------------------------------------------------------
// Palette state machine
// ---------------------------------------------------------------------------

enum PaletteState {
    /// Fuzzy-filtering the command list
    CommandFilter {
        query: String,
        selected: usize,
    },
    /// Selecting from a list of candidates (agents, projects)
    ArgSelect {
        arg_name: String,
        candidates: Vec<String>,
        selected: usize,
    },
    /// Free text input for args without a source
    ArgInput {
        arg_name: String,
        input: String,
    },
    /// Waiting for RunCommandResult
    Executing,
    /// Showing success/error briefly
    Result {
        success: bool,
        message: String,
    },
}

impl Default for PaletteState {
    fn default() -> Self {
        PaletteState::CommandFilter {
            query: String::new(),
            selected: 0,
        }
    }
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

#[derive(Default)]
struct ZchatPalette {
    state: PaletteState,

    // Discovered commands
    commands: Vec<CommandInfo>,
    command_names: Vec<String>,

    // Current command being built
    current_command: String,
    collected_args: Vec<String>,
    remaining_args: VecDeque<ArgInfo>,

    // Context from Zellij events
    project_name: String,
    agent_tabs: Vec<String>,
    session_names: Vec<String>,
}

register_plugin!(ZchatPalette);

impl ZchatPalette {
    fn discover_commands(&self) {
        let mut ctx = BTreeMap::new();
        ctx.insert("action".to_string(), "discover".to_string());
        run_command(&["zchat", "list-commands"], ctx);
    }

    fn execute_command(&mut self) {
        let parts: Vec<&str> = self.current_command.split_whitespace().collect();
        let mut cmd: Vec<String> = vec!["zchat".to_string()];
        if !self.project_name.is_empty() {
            cmd.push("--project".to_string());
            cmd.push(self.project_name.clone());
        }
        cmd.extend(parts.iter().map(|s| s.to_string()));
        cmd.extend(self.collected_args.iter().cloned());

        let cmd_refs: Vec<&str> = cmd.iter().map(|s| s.as_str()).collect();
        let mut ctx = BTreeMap::new();
        ctx.insert("action".to_string(), "execute".to_string());
        run_command(&cmd_refs, ctx);

        self.state = PaletteState::Executing;
    }

    fn advance_args(&mut self) {
        if let Some(arg) = self.remaining_args.pop_front() {
            match arg.source.as_deref() {
                Some("running_agents") => {
                    self.state = PaletteState::ArgSelect {
                        arg_name: arg.name,
                        candidates: self.agent_tabs.clone(),
                        selected: 0,
                    };
                }
                Some("projects") => {
                    self.state = PaletteState::ArgSelect {
                        arg_name: arg.name,
                        candidates: self.session_names.clone(),
                        selected: 0,
                    };
                }
                _ => {
                    self.state = PaletteState::ArgInput {
                        arg_name: arg.name,
                        input: String::new(),
                    };
                }
            }
        } else {
            self.execute_command();
        }
    }

    fn select_command(&mut self, query: &str, selected: usize) {
        let matches = fuzzy::fuzzy_filter(query, &self.command_names);
        if let Some(&(idx, _)) = matches.get(selected) {
            let cmd = &self.commands[idx];
            self.current_command = cmd.name.clone();
            self.collected_args.clear();
            self.remaining_args = cmd
                .args
                .iter()
                .filter(|a| a.required)
                .cloned()
                .collect();
            self.advance_args();
        }
    }

    fn update_agents_from_tabs(&mut self, tabs: &[TabInfo]) {
        self.agent_tabs.clear();
        for tab in tabs {
            let name = &tab.name;
            if SYSTEM_SUFFIXES.iter().any(|s| name.ends_with(s)) {
                continue;
            }
            if name.starts_with("Tab #") {
                continue;
            }
            self.agent_tabs.push(name.clone());
        }
    }

    fn update_sessions(&mut self, sessions: &[SessionInfo]) {
        self.session_names.clear();
        for session in sessions {
            if session.is_current_session {
                self.project_name = session
                    .name
                    .strip_prefix("zchat-")
                    .unwrap_or(&session.name)
                    .to_string();
            }
            if session.name.starts_with("zchat-") {
                self.session_names.push(
                    session
                        .name
                        .strip_prefix("zchat-")
                        .unwrap_or(&session.name)
                        .to_string(),
                );
            }
        }
    }

    fn handle_key(&mut self, key: KeyWithModifier) -> bool {
        match &mut self.state {
            PaletteState::CommandFilter { query, selected } => {
                match key.bare_key {
                    BareKey::Esc => {
                        hide_self();
                        return true;
                    }
                    BareKey::Enter => {
                        let q = query.clone();
                        let s = *selected;
                        self.select_command(&q, s);
                        return true;
                    }
                    BareKey::Up => {
                        *selected = selected.saturating_sub(1);
                        return true;
                    }
                    BareKey::Down => {
                        let max = fuzzy::fuzzy_filter(query, &self.command_names).len();
                        if *selected + 1 < max {
                            *selected += 1;
                        }
                        return true;
                    }
                    BareKey::Backspace => {
                        query.pop();
                        *selected = 0;
                        return true;
                    }
                    BareKey::Char(c) => {
                        query.push(c);
                        *selected = 0;
                        return true;
                    }
                    _ => {}
                }
            }
            PaletteState::ArgSelect {
                candidates,
                selected,
                ..
            } => {
                match key.bare_key {
                    BareKey::Esc => {
                        self.state = PaletteState::default();
                        return true;
                    }
                    BareKey::Enter => {
                        if let Some(val) = candidates.get(*selected) {
                            self.collected_args.push(val.clone());
                            self.advance_args();
                        }
                        return true;
                    }
                    BareKey::Up => {
                        *selected = selected.saturating_sub(1);
                        return true;
                    }
                    BareKey::Down => {
                        if *selected + 1 < candidates.len() {
                            *selected += 1;
                        }
                        return true;
                    }
                    _ => {}
                }
            }
            PaletteState::ArgInput { input, .. } => {
                match key.bare_key {
                    BareKey::Esc => {
                        self.state = PaletteState::default();
                        return true;
                    }
                    BareKey::Enter => {
                        let val = input.clone();
                        self.collected_args.push(val);
                        self.advance_args();
                        return true;
                    }
                    BareKey::Backspace => {
                        input.pop();
                        return true;
                    }
                    BareKey::Char(c) => {
                        input.push(c);
                        return true;
                    }
                    _ => {}
                }
            }
            PaletteState::Result { .. } => {
                // Any key dismisses the result
                self.state = PaletteState::default();
                hide_self();
                return true;
            }
            PaletteState::Executing => {}
        }
        false
    }

    fn render_filter(&self, rows: usize, _cols: usize, query: &str, selected: usize) {
        println!(" > {}_", query);

        let matches = fuzzy::fuzzy_filter(query, &self.command_names);
        let max_items = rows.saturating_sub(2);
        for (i, &(idx, _)) in matches.iter().take(max_items).enumerate() {
            let name = &self.command_names[idx];
            if i == selected {
                println!(" \x1b[7m> {}\x1b[0m", name);
            } else {
                println!("   {}", name);
            }
        }
        if matches.is_empty() && self.command_names.is_empty() {
            println!("   (loading commands...)");
        }
    }

    fn render_arg_select(
        &self,
        rows: usize,
        _cols: usize,
        arg_name: &str,
        candidates: &[String],
        selected: usize,
    ) {
        println!(" {} | select {}:", self.current_command, arg_name);

        let max_items = rows.saturating_sub(2);
        for (i, candidate) in candidates.iter().take(max_items).enumerate() {
            if i == selected {
                println!(" \x1b[7m> {}\x1b[0m", candidate);
            } else {
                println!("   {}", candidate);
            }
        }
    }

    fn render_arg_input(&self, _cols: usize, arg_name: &str, input: &str) {
        println!(" {} | enter {}:", self.current_command, arg_name);
        println!(" > {}_", input);
    }
}

impl ZellijPlugin for ZchatPalette {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        request_permission(&[
            PermissionType::ReadApplicationState,
            PermissionType::ChangeApplicationState,
            PermissionType::RunCommands,
        ]);
        subscribe(&[
            EventType::Key,
            EventType::TabUpdate,
            EventType::SessionUpdate,
            EventType::RunCommandResult,
        ]);
        self.discover_commands();
    }

    fn update(&mut self, event: Event) -> bool {
        match event {
            Event::Key(key) => self.handle_key(key),
            Event::TabUpdate(tabs) => {
                self.update_agents_from_tabs(&tabs);
                false
            }
            Event::SessionUpdate(sessions, _) => {
                self.update_sessions(&sessions);
                false
            }
            Event::RunCommandResult(exit_code, stdout, stderr, context) => {
                match context.get("action").map(|s| s.as_str()) {
                    Some("discover") => {
                        if exit_code == Some(0) {
                            if let Ok(text) = String::from_utf8(stdout) {
                                if let Ok(cmds) =
                                    serde_json::from_str::<Vec<CommandInfo>>(&text)
                                {
                                    self.command_names =
                                        cmds.iter().map(|c| c.name.clone()).collect();
                                    self.commands = cmds;
                                }
                            }
                        }
                        true
                    }
                    Some("execute") => {
                        let success = exit_code == Some(0);
                        let msg = if success {
                            "Done".to_string()
                        } else {
                            let err = String::from_utf8_lossy(&stderr);
                            if err.is_empty() {
                                "Command failed".to_string()
                            } else {
                                err.lines().next().unwrap_or("Error").to_string()
                            }
                        };
                        self.state = PaletteState::Result {
                            success,
                            message: msg,
                        };
                        true
                    }
                    _ => false,
                }
            }
            _ => false,
        }
    }

    fn render(&mut self, rows: usize, cols: usize) {
        match &self.state {
            PaletteState::CommandFilter { query, selected } => {
                let q = query.clone();
                let s = *selected;
                self.render_filter(rows, cols, &q, s);
            }
            PaletteState::ArgSelect {
                arg_name,
                candidates,
                selected,
            } => {
                let n = arg_name.clone();
                let c = candidates.clone();
                let s = *selected;
                self.render_arg_select(rows, cols, &n, &c, s);
            }
            PaletteState::ArgInput { arg_name, input } => {
                let n = arg_name.clone();
                let i = input.clone();
                self.render_arg_input(cols, &n, &i);
            }
            PaletteState::Executing => {
                println!(" Running: {} ...", self.current_command);
            }
            PaletteState::Result { success, message } => {
                let icon = if *success { "\u{2714}" } else { "\u{2718}" };
                println!(" {} {} (press any key)", icon, message);
            }
        }
    }
}
