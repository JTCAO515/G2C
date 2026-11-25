#if os(iOS)
import SwiftUI

extension LioTripHomeArrival {
    /// Arrival Mode for the trip home when the build turns it on (`G2CArrivalModeEnabled`), else nil, in which case
    /// its tasks are left out. Entry answers come only from Arrival Mode's sourced rules; the trip home never decides
    /// entry itself. The only write is ticking one of Arrival Mode's own checklist steps in its own progress.
    static func fromBuild(language: LioLanguage, defaults: UserDefaults = .standard) -> Self? {
        guard LioArrivalFeature.enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: LioArrivalFeature.infoKey)) else {
            return nil
        }
        return make(language: language, rules: try? LioArrivalRules.bundled(), defaults: defaults)
    }

    /// Separate from the build switch so the mapping can be tested with any rules and settings.
    static func make(language: LioLanguage, rules: LioArrivalRules?, defaults: UserDefaults) -> Self {
        func stored() -> String { defaults.string(forKey: LioArrivalProgress.storageKey) ?? "" }
        func arrivalDay(_ profile: LioTripProfile?) -> LioArrivalDay? {
            profile?.arrival.flatMap { LioArrivalDay($0.description) }
        }
        return Self(
            entry: { profile, nationality, now in
                LioTripHomeArrivalRules.entryStatus(rules: rules, profile: profile, nationality: nationality,
                                                    today: LioArrivalDay(date: now))
            },
            checklist: { LioTripHomeArrivalRules.checklist(stored: stored()) },
            setStep: { name, done in
                defaults.set(LioTripHomeArrivalRules.setting(name, done: done, in: stored()), forKey: LioArrivalProgress.storageKey)
            },
            entryPage: { profile in
                AnyView(LioArrivalEntryView(language: language, rules: rules,
                                            arrival: arrivalDay(profile)?.pickerDate() ?? .now,
                                            stayDays: LioArrivalTrip.formStayDays(profile?.stayDays ?? 7),
                                            onward: profile?.onwardToThirdCountry ?? false))
            },
            // Mobile data is a step of the checklist page; its own page is private to Arrival Mode.
            internetPage: { AnyView(LioArrivalView(language: language, rules: rules)) },
            checklistPage: { profile in
                AnyView(LioArrivalView(language: language, arrival: arrivalDay(profile), rules: rules))
            })
    }
}
#endif

/// The trip home's reading of Arrival Mode, without views, so it can be tested on any platform.
enum LioTripHomeArrivalRules {
    /// Arrival Mode's decision for the trip's details, or `.missingDetails` when the passport, the arrival day or
    /// the length of stay is not known (for example after the nationality was cleared at account deletion).
    static func entryStatus(rules: LioArrivalRules?, profile: LioTripProfile?, nationality: String,
                            today: LioArrivalDay) -> LioTripEntryStatus {
        guard !nationality.isEmpty, let arrival = profile?.arrival.flatMap({ LioArrivalDay($0.description) }),
              let stayDays = profile?.stayDays else { return .missingDetails }
        guard let rules else { return .officialOnly }
        let trip = LioArrivalTrip(countryCode: nationality, arrival: arrival, stayDays: stayDays,
                                  onwardToThirdCountry: profile?.onwardToThirdCountry ?? false)
        let decision = rules.evaluate(trip, today: today)
        switch decision.outcome {
        case .visaFree(let policy):
            return .visaFree(maxDays: policy.maxStayDays, checkedOn: policy.checkedAt.description)
        case .transit(let policy):
            return .transit(maxDays: policy.maxStayDays, checkedOn: policy.checkedAt.description,
                            summary: LioTripText(en: policy.summary.en, zh: policy.summary.zh))
        case .visaRequired:
            return .visaRequired(checkedOn: decision.checkedAt.description)
        case .checkOfficial:
            return .officialOnly
        }
    }

    /// Arrival Mode's ticked steps, by step name, from its own stored progress.
    static func checklist(stored: String) -> LioTripArrivalChecklist {
        let progress = LioArrivalProgress(stored: stored)
        return LioTripArrivalChecklist(done: Set(LioArrivalStep.allCases.filter(progress.isDone).map(\.rawValue)),
                                       total: LioArrivalStep.allCases.count)
    }

    /// Arrival Mode's progress with one step set; unknown step names change nothing.
    static func setting(_ name: String, done: Bool, in stored: String) -> String {
        var progress = LioArrivalProgress(stored: stored)
        guard let step = LioArrivalStep(rawValue: name) else { return stored }
        if progress.isDone(step) != done { progress.toggle(step) }
        return progress.stored
    }
}
