use zellij_tile::prelude::*;
use std::collections::{BTreeMap, VecDeque};

mod commands;
mod fuzzy;

use commands::{CommandInfo, ArgInfo};

/// System tab name suffixes that are not agents.
const SYSTEM_SUFFIXES: &[&str] = &["/chat", "/ctl"];

// ---------------------------------------------------------------------------
// Palette state machine
// ---------------------------------------------------------------------------

enum PaletteState {
    /// Fuzzy-filtering the command list
    CommandFilter {
        query: String,
        selected: usize,
    },
    /// Selecting from a list of candidates (agents, projects, servers)
    ArgSelect {
        arg_name: String,
        candidates: Vec<String>, // display labels
        values: Vec<String>,     // actual values passed to CLI
        selected: usize,
    },
    /// Free text input for args without a source
    ArgInput {
        arg_name: String,
        input: String,
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

    // Configuration from KDL
    zchat_bin: String,

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
    fn load_commands_from_config(&mut self, json_str: &str) {
        if let Some(cmds) = commands::parse_commands(json_str) {
            self.command_names = commands::command_names(&cmds);
            self.commands = cmds;
        }
    }

    fn execute_command(&mut self) {
        let cmd = commands::build_cli_args(
            &self.zchat_bin,
            &self.project_name,
            &self.current_command,
            &self.collected_args,
        );

        if cmd.is_empty() {
            return;
        }

        // Open a floating terminal pane running the CLI command.
        // User interacts with the real CLI (prompts, validation, output).
        let path = std::path::PathBuf::from(&cmd[0]);
        let args: Vec<String> = cmd[1..].to_vec();
        let command = CommandToRun {
            path,
            args,
            cwd: None,
        };
        open_command_pane_floating(command, None, BTreeMap::new());
        hide_self();
        self.state = PaletteState::default();
    }

    fn advance_args(&mut self) {
        if let Some(arg) = self.remaining_args.pop_front() {
            // 1. Pre-resolved choices from CLI (static: servers, templates, etc.)
            if !arg.choices.is_empty() {
                let labels: Vec<String> = arg.choices.iter().map(|c| c.label.clone()).collect();
                let vals: Vec<String> = arg.choices.iter().map(|c| c.value.clone()).collect();
                self.state = PaletteState::ArgSelect {
                    arg_name: arg.name,
                    candidates: labels,
                    values: vals,
                    selected: 0,
                };
                return;
            }
            // 2. Runtime sources from Zellij events
            match arg.source.as_deref() {
                Some("running_agents") => {
                    let tabs = self.agent_tabs.clone();
                    self.state = PaletteState::ArgSelect {
                        arg_name: arg.name,
                        candidates: tabs.clone(),
                        values: tabs,
                        selected: 0,
                    };
                }
                Some("projects") => {
                    let sessions = self.session_names.clone();
                    self.state = PaletteState::ArgSelect {
                        arg_name: arg.name,
                        candidates: sessions.clone(),
                        values: sessions,
                        selected: 0,
                    };
                }
                // 3. Free text input
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
            // Only collect required positional args in palette.
            // Optional args are handled by CLI's interactive prompts
            // in the terminal pane opened by execute_command().
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
                // "zchat-local" → "local", but "zchat" (main session) → ""
                self.project_name = session
                    .name
                    .strip_prefix("zchat-")
                    .unwrap_or("")
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
                arg_name: _,
                values,
                candidates,
                selected,
            } => {
                match key.bare_key {
                    BareKey::Esc => {
                        self.state = PaletteState::default();
                        return true;
                    }
                    BareKey::Enter => {
                        if let Some(val) = values.get(*selected) {
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
            PaletteState::ArgInput { arg_name: _, input } => {
                match key.bare_key {
                    BareKey::Esc => {
                        self.state = PaletteState::default();
                        return true;
                    }
                    BareKey::Enter => {
                        if !input.is_empty() {
                            self.collected_args.push(input.clone());
                            self.advance_args();
                        }
                        // Empty: do nothing (must provide value)
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
        println!(" {} | {}:", self.current_command, arg_name);
        println!(" > {}_", input);
    }
}

impl ZellijPlugin for ZchatPalette {
    fn load(&mut self, configuration: BTreeMap<String, String>) {
        request_permission(&[
            PermissionType::ReadApplicationState,
            PermissionType::ChangeApplicationState,
            PermissionType::RunCommands,
        ]);
        subscribe(&[
            EventType::Key,
            EventType::TabUpdate,
            EventType::SessionUpdate,
        ]);

        // Read configuration from KDL
        self.zchat_bin = configuration
            .get("zchat_bin")
            .cloned()
            .unwrap_or_else(|| "zchat".to_string());

        // Load commands from inline JSON (passed via KDL config)
        if let Some(json_str) = configuration.get("commands_json") {
            self.load_commands_from_config(json_str);
        }
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
                ..
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
        }
    }
}
