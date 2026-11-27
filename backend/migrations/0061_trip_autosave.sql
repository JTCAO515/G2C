-- local runtime only: #1994 (T-1, ADR-0012), who wrote each Trip item, what a person deleted, and
-- when each version was committed. New tables only; no column is added to an existing table.
-- All three are append-only: the runtime role can SELECT and INSERT (no UPDATE, no DELETE grant),
-- a trigger refuses UPDATE and TRUNCATE for every role, and only the account cleanup login
-- (cj_local_cleanup, purpose 'account', the existing business/trip-authoritative hook) can delete.
-- No SECURITY DEFINER, no new role.

-- Origin of every item of every committed version: 'lio' (written by Lio) or 'user' (touched by
-- the person). Written in the same transaction as the version, by the sole commit point.
CREATE TABLE public.cj_trip_item_origin (
 scope text NOT NULL,
 trip_id text NOT NULL,
 trip_version bigint NOT NULL CHECK(trip_version>0),
 item_id text NOT NULL CHECK(item_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 origin text NOT NULL CHECK(origin IN ('lio','user')),
 PRIMARY KEY(scope,trip_id,trip_version,item_id),
 FOREIGN KEY(scope,trip_id) REFERENCES public.cj_trip_record(scope,trip_id)
);

-- An item a person's write removed. Lio may not add the same item id, or the same Gaode place,
-- back to this Trip. amap_id is NULL for an item without a matched Gaode place.
CREATE TABLE public.cj_trip_item_tombstone (
 scope text NOT NULL,
 trip_id text NOT NULL,
 item_id text NOT NULL CHECK(item_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 amap_id text CHECK(amap_id IS NULL OR (octet_length(amap_id) BETWEEN 1 AND 200 AND amap_id !~ '[[:cntrl:]]')),
 trip_version bigint NOT NULL CHECK(trip_version>0),
 PRIMARY KEY(scope,trip_id,trip_version,item_id),
 FOREIGN KEY(scope,trip_id) REFERENCES public.cj_trip_record(scope,trip_id)
);

-- Database time of every accepted commit receipt, and whether it was an automatic Lio save.
CREATE TABLE public.cj_trip_commit_time (
 scope text NOT NULL,
 action_id text NOT NULL,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 autosave boolean NOT NULL,
 PRIMARY KEY(scope,action_id),
 FOREIGN KEY(scope,action_id) REFERENCES public.cj_trip_receipt(scope,action_id)
);

ALTER TABLE public.cj_trip_item_origin ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_trip_item_origin FORCE ROW LEVEL SECURITY;
ALTER TABLE public.cj_trip_item_tombstone ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_trip_item_tombstone FORCE ROW LEVEL SECURITY;
ALTER TABLE public.cj_trip_commit_time ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_trip_commit_time FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.cj_trip_item_origin,public.cj_trip_item_tombstone,public.cj_trip_commit_time FROM PUBLIC;

CREATE POLICY cj_trip_item_origin_owner ON public.cj_trip_item_origin TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
CREATE POLICY cj_trip_item_tombstone_owner ON public.cj_trip_item_tombstone TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
CREATE POLICY cj_trip_commit_time_owner ON public.cj_trip_commit_time TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
CREATE POLICY account_retired ON public.cj_trip_item_origin AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON public.cj_trip_item_tombstone AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON public.cj_trip_commit_time AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON public.cj_trip_item_origin,public.cj_trip_item_tombstone,public.cj_trip_commit_time TO cj_m1_runtime;

-- Account erasure only (same predicate as the other Trip tables in 0032, without the memory purpose:
-- memory cleanup keeps accepted Trip versions, and these rows belong to accepted versions only).
CREATE POLICY cj_cleanup_owner ON public.cj_trip_item_origin FOR SELECT TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
CREATE POLICY cj_cleanup_delete ON public.cj_trip_item_origin FOR DELETE TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
CREATE POLICY cj_cleanup_owner ON public.cj_trip_item_tombstone FOR SELECT TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
CREATE POLICY cj_cleanup_delete ON public.cj_trip_item_tombstone FOR DELETE TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
CREATE POLICY cj_cleanup_owner ON public.cj_trip_commit_time FOR SELECT TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
CREATE POLICY cj_cleanup_delete ON public.cj_trip_commit_time FOR DELETE TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true) IN ('account') AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose=current_setting('cj.cleanup_purpose',true) AND NOT o.blocked));
GRANT SELECT,DELETE ON public.cj_trip_item_origin,public.cj_trip_item_tombstone,public.cj_trip_commit_time TO cj_local_cleanup;

-- Origins are written for the version being committed (the current record version) and are
-- monotonic: an item that was 'user' in the version before stays 'user' while it is present.
CREATE FUNCTION public.cj_trip_item_origin_order() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.cj_trip_record
                   WHERE scope=NEW.scope AND trip_id=NEW.trip_id AND version=NEW.trip_version) THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='item origin only for the committed Trip version';
    END IF;
    IF NEW.origin='lio' AND EXISTS(SELECT 1 FROM public.cj_trip_item_origin
            WHERE scope=NEW.scope AND trip_id=NEW.trip_id AND trip_version=NEW.trip_version-1
              AND item_id=NEW.item_id AND origin='user') THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='item origin cannot return from user to lio';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_trip_item_origin_order() FROM PUBLIC;
CREATE TRIGGER cj_trip_item_origin_order BEFORE INSERT ON public.cj_trip_item_origin
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_item_origin_order();

CREATE FUNCTION public.cj_trip_item_tombstone_order() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.cj_trip_record
                   WHERE scope=NEW.scope AND trip_id=NEW.trip_id AND version=NEW.trip_version) THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='tombstone only for the committed Trip version';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_trip_item_tombstone_order() FROM PUBLIC;
CREATE TRIGGER cj_trip_item_tombstone_order BEFORE INSERT ON public.cj_trip_item_tombstone
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_item_tombstone_order();

-- The time is the database clock at insert, never a caller value; only accepted receipts.
CREATE FUNCTION public.cj_trip_commit_time_order() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.cj_trip_receipt
                   WHERE scope=NEW.scope AND action_id=NEW.action_id AND kind='accept') THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='commit time only for an accepted receipt';
    END IF;
    NEW.committed_at := clock_timestamp();
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_trip_commit_time_order() FROM PUBLIC;
CREATE TRIGGER cj_trip_commit_time_order BEFORE INSERT ON public.cj_trip_commit_time
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_commit_time_order();

CREATE FUNCTION public.cj_trip_autosave_append_only() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Trip origin, tombstone and commit time records are append-only';
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_trip_autosave_append_only() FROM PUBLIC;
CREATE TRIGGER cj_trip_item_origin_no_update BEFORE UPDATE ON public.cj_trip_item_origin
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_item_origin_no_truncate BEFORE TRUNCATE ON public.cj_trip_item_origin
 FOR EACH STATEMENT EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_item_tombstone_no_update BEFORE UPDATE ON public.cj_trip_item_tombstone
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_item_tombstone_no_truncate BEFORE TRUNCATE ON public.cj_trip_item_tombstone
 FOR EACH STATEMENT EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_commit_time_no_update BEFORE UPDATE ON public.cj_trip_commit_time
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_commit_time_no_truncate BEFORE TRUNCATE ON public.cj_trip_commit_time
 FOR EACH STATEMENT EXECUTE FUNCTION public.cj_trip_autosave_append_only();
