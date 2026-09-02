# QA Toolbox — Automated Test Cases

Full list of the 122 automated test cases in `tests/` (pytest). Generated from `pytest --collect-only`; each entry is one test function, grouped by its test module.

## API Client (13)
`tests/test_api_client.py`

- Move request into folder updates folder and collection — `test_move_request_into_folder_updates_folder_and_collection`
- Move request to collection root clears folder — `test_move_request_to_collection_root_clears_folder`
- Move request rejects folder from a different collection — `test_move_request_rejects_folder_from_a_different_collection`
- Move request returns 404 for unknown request — `test_move_request_returns_404_for_unknown_request`
- Strip json line comments removes commented lines — `test_strip_json_line_comments_removes_commented_lines`
- Strip json line comments drops dangling trailing comma — `test_strip_json_line_comments_drops_dangling_trailing_comma`
- Strip json line comments preserves slashes inside strings — `test_strip_json_line_comments_preserves_slashes_inside_strings`
- Body for wire leaves already valid json untouched — `test_body_for_wire_leaves_already_valid_json_untouched`
- Body for wire leaves non json untouched — `test_body_for_wire_leaves_non_json_untouched`
- Body for wire leaves body alone if stripping still invalid — `test_body_for_wire_leaves_body_alone_if_stripping_still_invalid`
- Body for wire handles empty body — `test_body_for_wire_handles_empty_body`
- Send disables tls verification — `test_send_disables_tls_verification`
- Resolve endpoint strips comments from curl preview — `test_resolve_endpoint_strips_comments_from_curl_preview`

## Bugs (4)
`tests/test_bugs.py`

- Create bug with defaults — `test_create_bug_with_defaults`
- Create bug duplicate code within subtask — `test_create_bug_duplicate_code_within_subtask`
- Edit bug severity and status — `test_edit_bug_severity_and_status`
- Bug list route — `test_bug_list_route`

## DOCX Builder (10)
`tests/test_docx_builder.py`

- Build docx header and single step — `test_build_docx_header_and_single_step`
- Build docx clones tables for multiple steps — `test_build_docx_clones_tables_for_multiple_steps`
- Build docx inserts screenshots — `test_build_docx_inserts_screenshots`
- Build docx screenshots do not accumulate across cloned step tables — `test_build_docx_screenshots_do_not_accumulate_across_cloned_step_tables`
- Build docx preserves data test field despite cell index anomaly — `test_build_docx_preserves_data_test_field_despite_cell_index_anomaly`
- Build docx handles unembeddable screenshot without crashing — `test_build_docx_handles_unembeddable_screenshot_without_crashing`
- Build docx unwraps content controls and writes test date once — `test_build_docx_unwraps_content_controls_and_writes_test_date_once`
- Build docx renders data test as bullet list — `test_build_docx_renders_data_test_as_bullet_list`
- Build docx screenshots are 18cm wide and centered — `test_build_docx_screenshots_are_18cm_wide_and_centered`
- Project and scenario codes are tracker hyperlinks — `test_project_and_scenario_codes_are_tracker_hyperlinks`

## DOCX Export (2)
`tests/test_docx_export.py`

- Export docx downloads file — `test_export_docx_downloads_file`
- Export docx 404 for missing testcase — `test_export_docx_404_for_missing_testcase`

## Dashboard (1)
`tests/test_dashboard.py`

- Dashboard shows story and counts — `test_dashboard_shows_story_and_counts`

## Database Migration Helpers (3)
`tests/test_database_migration.py`

- Ensure columns adds only missing columns — `test_ensure_columns_adds_only_missing_columns`
- Backfill column copies only into empty destinations — `test_backfill_column_copies_only_into_empty_destinations`
- Migrate table copies rows and drops the source — `test_migrate_table_copies_rows_and_drops_the_source`

## Image / Screenshot Export (6)
`tests/test_image_export.py`

- Export images zip names entries by section step and name — `test_export_images_zip_names_entries_by_section_step_and_name`
- Export images zip disambiguates multiple shots on one step — `test_export_images_zip_disambiguates_multiple_shots_on_one_step`
- Export images 404 for missing testcase — `test_export_images_404_for_missing_testcase`
- Export docx filename is code and title — `test_export_docx_filename_is_code_and_title`
- Delete testcase removes screenshot files from disk — `test_delete_testcase_removes_screenshot_files_from_disk`
- Delete subtask removes screenshot files from disk — `test_delete_subtask_removes_screenshot_files_from_disk`

## Models (9)
`tests/test_models.py`

- Story display code globally unique — `test_story_display_code_globally_unique`
- Phase type unique per story — `test_phase_type_unique_per_story`
- Subtask display code unique within phase — `test_subtask_display_code_unique_within_phase`
- Testcase display code unique within subtask — `test_testcase_display_code_unique_within_subtask`
- Testcase defaults — `test_testcase_defaults`
- Testcase step ordering — `test_testcase_step_ordering`
- Bug display code unique within subtask — `test_bug_display_code_unique_within_subtask`
- Bug defaults — `test_bug_defaults`
- Note create — `test_note_create`

## Note Section (7)
`tests/test_notes.py`

- Create note attached to story — `test_create_note_attached_to_story`
- Note panel displays content verbatim — `test_note_panel_displays_content_verbatim`
- Note without remark has no remark shown — `test_note_without_remark_has_no_remark_shown`
- Delete note — `test_delete_note`
- Update note saves content remark and language — `test_update_note_saves_content_remark_and_language`
- Update note returns 404 for unknown note — `test_update_note_returns_404_for_unknown_note`
- Note attached to subtask — `test_note_attached_to_subtask`

## Prebuilt Test Cases (11)
`tests/test_prebuilt.py`

- New prebuilt starts with the three default sections — `test_new_prebuilt_starts_with_the_three_default_sections`
- Prebuilt sections can be reordered — `test_prebuilt_sections_can_be_reordered`
- Prebuilt reorder rejects ids from another prebuilt — `test_prebuilt_reorder_rejects_ids_from_another_prebuilt`
- Prebuilt steps can be added and listed — `test_prebuilt_steps_can_be_added_and_listed`
- Creating a testcase from a prebuilt copies its steps — `test_creating_a_testcase_from_a_prebuilt_copies_its_steps`
- Creating a blank testcase has three empty sections — `test_creating_a_blank_testcase_has_three_empty_sections`
- Editing a prebuilt does not change cases already created from it — `test_editing_a_prebuilt_does_not_change_cases_already_created_from_it`
- Prebuilt service name test type and remark round trip — `test_prebuilt_service_name_test_type_and_remark_round_trip`
- Creating a testcase from a prebuilt prefills test type and remark — `test_creating_a_testcase_from_a_prebuilt_prefills_test_type_and_remark`
- New testcase modal exposes search filter and title autofill hooks — `test_new_testcase_modal_exposes_search_filter_and_title_autofill_hooks`
- Save an existing testcase as a prebuilt — `test_save_an_existing_testcase_as_a_prebuilt`

## Screenshots (4)
`tests/test_screenshots.py`

- Upload and delete screenshot — `test_upload_and_delete_screenshot`
- Deleting step removes screenshot file — `test_deleting_step_removes_screenshot_file`
- Upload returns json when requested — `test_upload_returns_json_when_requested`
- Upload still redirects for a plain form post — `test_upload_still_redirects_for_a_plain_form_post`

## Smoke Tests (3)
`tests/test_smoke.py`

- App boots — `test_app_boots`
- Base layout renders nav — `test_base_layout_renders_nav`
- Full workflow story to docx export — `test_full_workflow_story_to_docx_export`

## Stories / Phases (7)
`tests/test_stories.py`

- Create story — `test_create_story`
- Create story duplicate code shows inline error — `test_create_story_duplicate_code_shows_inline_error`
- Delete story blocked when phase exists — `test_delete_story_blocked_when_phase_exists`
- Create phase rejects duplicate type — `test_create_phase_rejects_duplicate_type`
- Delete empty phase succeeds — `test_delete_empty_phase_succeeds`
- Delete phase blocked when subtasks exist — `test_delete_phase_blocked_when_subtasks_exist`
- Delete phase not found returns 404 — `test_delete_phase_not_found_returns_404`

## Subtasks (3)
`tests/test_subtasks.py`

- Create subtask — `test_create_subtask`
- Staging after rollback restricts to single execution subtask — `test_staging_after_rollback_restricts_to_single_execution_subtask`
- Delete subtask cascades to testcases and bugs — `test_delete_subtask_cascades_to_testcases_and_bugs`

## Test Case Execution Page (4)
`tests/test_execution.py`

- Execute page renders — `test_execute_page_renders`
- Add step and ordering — `test_add_step_and_ordering`
- Update section1 fields — `test_update_section1_fields`
- Edit and delete step — `test_edit_and_delete_step`

## Test Case Import / Export (20)
`tests/test_testcase_io.py`

- Testcase round trip — `test_testcase_round_trip`
- Testcase import auto renames on collision — `test_testcase_import_auto_renames_on_collision`
- Testcase import rejects wrong kind — `test_testcase_import_rejects_wrong_kind`
- Subtask round trip — `test_subtask_round_trip`
- Subtask import rejects disallowed type for target phase — `test_subtask_import_rejects_disallowed_type_for_target_phase`
- Subtask import auto renames colliding bug — `test_subtask_import_auto_renames_colliding_bug`
- Task round trip — `test_task_round_trip`
- Task import rejects duplicate phase type — `test_task_import_rejects_duplicate_phase_type`
- Export json endpoint returns valid shape — `test_export_json_endpoint_returns_valid_shape`
- Import subtask endpoint flashes error on bad json — `test_import_subtask_endpoint_flashes_error_on_bad_json`
- Import testcase endpoint happy path — `test_import_testcase_endpoint_happy_path`
- Testcases to dict and extract round trip — `test_testcases_to_dict_and_extract_round_trip`
- Extract testcase candidates from single testcase — `test_extract_testcase_candidates_from_single_testcase`
- Extract testcase candidates from subtask ignores bugs — `test_extract_testcase_candidates_from_subtask_ignores_bugs`
- Extract testcase candidates rejects unknown kind — `test_extract_testcase_candidates_rejects_unknown_kind`
- Export selected testcases endpoint only includes checked ids — `test_export_selected_testcases_endpoint_only_includes_checked_ids`
- Export selected testcases endpoint flashes when none selected — `test_export_selected_testcases_endpoint_flashes_when_none_selected`
- Import preview endpoint lists every candidate — `test_import_preview_endpoint_lists_every_candidate`
- Import confirm endpoint only creates selected rows — `test_import_confirm_endpoint_only_creates_selected_rows`
- Import confirm endpoint flashes when nothing selected — `test_import_confirm_endpoint_flashes_when_nothing_selected`

## Test Case Sections (9)
`tests/test_sections.py`

- New testcase starts with the three default sections — `test_new_testcase_starts_with_the_three_default_sections`
- Sections can repeat and keep the order they were added — `test_sections_can_repeat_and_keep_the_order_they_were_added`
- Steps belong to their own section instance — `test_steps_belong_to_their_own_section_instance`
- Deleting a section removes only its own steps — `test_deleting_a_section_removes_only_its_own_steps`
- Export renders every section in order — `test_export_renders_every_section_in_order`
- Image zip disambiguates repeated section kinds — `test_image_zip_disambiguates_repeated_section_kinds`
- Sections can be reordered — `test_sections_can_be_reordered`
- Reorder rejects ids from another testcase — `test_reorder_rejects_ids_from_another_testcase`
- Reorder survives in the export — `test_reorder_survives_in_the_export`

## Test Cases (6)
`tests/test_testcases.py`

- Create testcase defaults to to do — `test_create_testcase_defaults_to_to_do`
- Create testcase duplicate code within subtask — `test_create_testcase_duplicate_code_within_subtask`
- Edit testcase code and title — `test_edit_testcase_code_and_title`
- Delete testcase cascades to its steps — `test_delete_testcase_cascades_to_its_steps`
- Status dropdown offers to do and back log — `test_status_dropdown_offers_to_do_and_back_log`
- Status can be set to back log — `test_status_can_be_set_to_back_log`

