-- Add only the reviewed draft outcome event. Applied migration 3 remains unchanged.
-- The original CREATE TABLE names these constraints deterministically; missing
-- constraints cause this migration to fail rather than drop an unrelated guard.
ALTER TABLE public.cj_run_event
  DROP CONSTRAINT cj_run_event_kind_check,
  DROP CONSTRAINT cj_run_event_check,
  ADD CONSTRAINT cj_run_event_kind_check CHECK
    (kind IN ('started','text_delta','effect_committed','completed','failed',
              'cancelled','context_invalid','unknown','draft_outcome')),
  ADD CONSTRAINT cj_run_event_check CHECK
    ((kind IN ('text_delta','effect_committed') AND length(value)>0)
     OR (kind='draft_outcome' AND value IN ('validation_failed','provider_failed','provider_unknown'))
     OR (kind NOT IN ('text_delta','effect_committed','draft_outcome') AND value=''));
