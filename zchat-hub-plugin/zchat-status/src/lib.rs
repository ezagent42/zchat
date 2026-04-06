use zellij_tile::prelude::*;
use std::collections::BTreeMap;

/// System tab name suffixes that are not agents.
const SYSTEM_SUFFIXES: &[&str] = &["/chat", "/ctl"];

#[derive(Default)]
struct ZchatStatus {
    project_name: String,
    total_agents: usize,
}

register_plugin!(ZchatStatus);

impl ZchatStatus {
    fn update_from_tabs(&mut self, tabs: &[TabInfo]) {
        let mut total = 0usize;
        for tab in tabs {
            let name = &tab.name;
            if SYSTEM_SUFFIXES.iter().any(|s| name.ends_with(s)) {
                continue;
            }
            if name.starts_with("Tab #") {
                continue;
            }
            total += 1;
        }
        self.total_agents = total;
    }

    fn update_project_name(&mut self, sessions: &[SessionInfo]) {
        for session in sessions {
            if session.is_current_session {
                self.project_name = session
                    .name
                    .strip_prefix("zchat-")
                    .unwrap_or(&session.name)
                    .to_string();
                break;
            }
        }
    }
}

impl ZellijPlugin for ZchatStatus {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        set_selectable(false);
        request_permission(&[PermissionType::ReadApplicationState]);
        subscribe(&[EventType::TabUpdate, EventType::SessionUpdate]);
    }

    fn update(&mut self, event: Event) -> bool {
        match event {
            Event::TabUpdate(tabs) => {
                self.update_from_tabs(&tabs);
                true
            }
            Event::SessionUpdate(sessions, _) => {
                self.update_project_name(&sessions);
                true
            }
            _ => false,
        }
    }

    fn render(&mut self, _rows: usize, cols: usize) {
        let name = if self.project_name.is_empty() {
            "zchat"
        } else {
            &self.project_name
        };
        let status = format!(
            " {} \u{2502} agents: {}",
            name, self.total_agents,
        );
        let text = Text::new(&status).color_range(0, 1..=name.len());
        print_text_with_coordinates(text, 0, 0, Some(cols), None);
    }
}
