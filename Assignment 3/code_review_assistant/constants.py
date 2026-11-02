"""Single source of truth for session-state keys shared between agents and tools.
Keys prefixed with `user:` persist across sessions for the same user."""


class StateKeys:
    CODE_TO_REVIEW = "code_to_review"
    CODE_ANALYSIS = "code_analysis"
    STYLE_SCORE = "style_score"
    STYLE_ISSUES = "style_issues"
    TEST_RESULTS = "test_execution_summary"
    FINAL_FEEDBACK = "final_feedback"
    CODE_FIXES = "code_fixes"
    FIXED_STYLE_SCORE = "fixed_style_score"
    FIX_TEST_RESULTS = "fix_test_execution_summary"
    FIX_REPORT = "fix_report"
    FIX_STATUS = "fix_status"
    REVIEW_HISTORY = "user:review_history"
    SUBMISSION_COUNT = "user:submission_count"
