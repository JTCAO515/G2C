-- Task-private empty PostgreSQL only (scripts/pg_suites.py trip group, after candidate.sql): the
-- 0061 tables, FKs and order triggers without roles, RLS or the TRUNCATE guard, so the bare
-- fixture can reset between tests. The migration chain uses backend/migrations/0061_trip_autosave.sql.
CREATE TABLE public.cj_trip_item_origin (
 scope text NOT NULL,
 trip_id text NOT NULL,
 trip_version bigint NOT NULL CHECK(trip_version>0),
 item_id text NOT NULL CHECK(item_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 origin text NOT NULL CHECK(origin IN ('lio','user')),
 PRIMARY KEY(scope,trip_id,trip_version,item_id),
 FOREIGN KEY(scope,trip_id) REFERENCES public.cj_trip_record(scope,trip_id)
);
CREATE TABLE public.cj_trip_item_tombstone (
 scope text NOT NULL,
 trip_id text NOT NULL,
 item_id text NOT NULL CHECK(item_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 amap_id text CHECK(amap_id IS NULL OR (octet_length(amap_id) BETWEEN 1 AND 200 AND amap_id !~ '[[:cntrl:]]')),
 trip_version bigint NOT NULL CHECK(trip_version>0),
 PRIMARY KEY(scope,trip_id,trip_version,item_id),
 FOREIGN KEY(scope,trip_id) REFERENCES public.cj_trip_record(scope,trip_id)
);
CREATE TABLE public.cj_trip_commit_time (
 scope text NOT NULL,
 action_id text NOT NULL,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 autosave boolean NOT NULL,
 PRIMARY KEY(scope,action_id),
 FOREIGN KEY(scope,action_id) REFERENCES public.cj_trip_receipt(scope,action_id)
);
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
CREATE FUNCTION public.cj_trip_autosave_append_only() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Trip origin, tombstone and commit time records are append-only';
END;
$$;
CREATE TRIGGER cj_trip_item_origin_order BEFORE INSERT ON public.cj_trip_item_origin
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_item_origin_order();
CREATE TRIGGER cj_trip_item_tombstone_order BEFORE INSERT ON public.cj_trip_item_tombstone
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_item_tombstone_order();
CREATE TRIGGER cj_trip_commit_time_order BEFORE INSERT ON public.cj_trip_commit_time
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_commit_time_order();
CREATE TRIGGER cj_trip_item_origin_no_update BEFORE UPDATE ON public.cj_trip_item_origin
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_item_tombstone_no_update BEFORE UPDATE ON public.cj_trip_item_tombstone
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
CREATE TRIGGER cj_trip_commit_time_no_update BEFORE UPDATE ON public.cj_trip_commit_time
 FOR EACH ROW EXECUTE FUNCTION public.cj_trip_autosave_append_only();
