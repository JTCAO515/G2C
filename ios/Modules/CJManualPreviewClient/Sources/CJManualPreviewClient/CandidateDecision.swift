/// Original decision outcome shared by the candidate clients.
public enum CandidateDecision<Receipt: Sendable>: Sendable {
    case confirmed(Receipt), unknown, rejected(Int)
}
