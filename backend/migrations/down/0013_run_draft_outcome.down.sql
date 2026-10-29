-- Lock before inspecting rows so a concurrent append cannot race rollback.
LOCK TABLE public.cj_run_event IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.cj_run_event WHERE kind='draft_outcome') THEN
    RAISE EXCEPTION 'draft outcome events exist; retain compatible reader, no destructive rollback';
  END IF;
END $$;
ALTER TABLE public.cj_run_event
  DROP CONSTRAINT cj_run_event_kind_check,
  DROP CONSTRAINT cj_run_event_check,
  ADD CONSTRAINT cj_run_event_kind_check CHECK
    (kind IN ('started','text_delta','effect_committed','completed','failed',
              'cancelled','context_invalid','unknown')),
  ADD CONSTRAINT cj_run_event_check CHECK
    ((kind IN ('text_delta','effect_committed') AND length(value)>0)
     OR (kind NOT IN ('text_delta','effect_committed') AND value=''));
