/// Score a query against a target string using fuzzy subsequence matching.
/// Returns None if the query doesn't match.
/// Higher score = better match. Bonuses for consecutive chars and word starts.
pub fn fuzzy_score(query: &str, target: &str) -> Option<i32> {
    if query.is_empty() {
        return Some(0);
    }

    let query_lower: Vec<char> = query.to_lowercase().chars().collect();
    let target_lower: Vec<char> = target.to_lowercase().chars().collect();
    let target_chars: Vec<char> = target.chars().collect();

    let mut score: i32 = 0;
    let mut qi = 0;
    let mut prev_match_idx: Option<usize> = None;

    for (ti, &tc) in target_lower.iter().enumerate() {
        if qi < query_lower.len() && tc == query_lower[qi] {
            score += 1;

            // Consecutive match bonus
            if let Some(prev) = prev_match_idx {
                if ti == prev + 1 {
                    score += 3;
                }
            }

            // Start-of-word bonus (first char or after separator)
            if ti == 0
                || matches!(
                    target_chars.get(ti.wrapping_sub(1)),
                    Some(' ' | '-' | '_' | '/')
                )
            {
                score += 5;
            }

            prev_match_idx = Some(ti);
            qi += 1;
        }
    }

    if qi == query_lower.len() {
        Some(score)
    } else {
        None
    }
}

/// Filter and sort items by fuzzy match score. Returns (index, score) pairs, best first.
pub fn fuzzy_filter(query: &str, items: &[String]) -> Vec<(usize, i32)> {
    let mut scored: Vec<(usize, i32)> = items
        .iter()
        .enumerate()
        .filter_map(|(i, item)| fuzzy_score(query, item).map(|s| (i, s)))
        .collect();
    scored.sort_by(|a, b| b.1.cmp(&a.1));
    scored
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_query_matches_everything() {
        assert_eq!(fuzzy_score("", "anything"), Some(0));
    }

    #[test]
    fn exact_match_scores_high() {
        let exact = fuzzy_score("agent create", "agent create").unwrap();
        let partial = fuzzy_score("ag cr", "agent create").unwrap();
        assert!(exact > partial);
    }

    #[test]
    fn no_match_returns_none() {
        assert_eq!(fuzzy_score("xyz", "agent create"), None);
    }

    #[test]
    fn case_insensitive() {
        assert!(fuzzy_score("AG", "agent").is_some());
    }

    #[test]
    fn word_start_bonus() {
        // "ac" should score higher on "agent create" (both chars at word starts)
        // than on "abcdefghijklmnop create" (only 'a' at start)
        let word_start = fuzzy_score("ac", "agent create").unwrap();
        let mid_word = fuzzy_score("ac", "axxc").unwrap();
        assert!(word_start > mid_word);
    }

    #[test]
    fn filter_sorts_by_score() {
        let items: Vec<String> = vec![
            "project create".into(),
            "agent create".into(),
            "agent restart".into(),
        ];
        let results = fuzzy_filter("ag cr", &items);
        assert!(!results.is_empty());
        assert_eq!(results[0].0, 1); // "agent create" should be first
    }

    #[test]
    fn filter_excludes_non_matches() {
        let items: Vec<String> = vec!["agent create".into(), "shutdown".into()];
        let results = fuzzy_filter("xyz", &items);
        assert!(results.is_empty());
    }
}
