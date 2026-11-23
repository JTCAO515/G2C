#if os(iOS)
@preconcurrency import CoreLocation
import Foundation

@MainActor final class LioTaxiPickupLocation: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var pending: CheckedContinuation<LioTaxiPlace, any Error>?
    private var timeout: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
    }

    var permissionWasDenied: Bool {
        manager.authorizationStatus == .denied || manager.authorizationStatus == .restricted
    }

    func pickup() async throws -> LioTaxiPlace {
        try Task.checkCancellation()
        guard pending == nil else { throw LioTaxiFailure.locationDenied }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                pending = continuation
                if Task.isCancelled {
                    finish(.failure(CancellationError()))
                } else if manager.authorizationStatus == .notDetermined {
                    manager.requestWhenInUseAuthorization()
                } else {
                    requestIfAuthorized()
                }
            }
        } onCancel: {
            Task { @MainActor in self.finish(.failure(CancellationError())) }
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor [weak self] in
            guard let self, pending != nil, self.manager.authorizationStatus != .notDetermined else { return }
            requestIfAuthorized()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let coordinate = locations.last(where: { $0.horizontalAccuracy >= 0 })?.coordinate
        let pickup = coordinate.map {
            LioTaxiPlace(nameZH: "当前位置", nameEN: "Current location", addressZH: nil,
                         coordinate: .init(latitude: $0.latitude, longitude: $0.longitude, referenceSystem: .wgs84))
        }
        Task { @MainActor [weak self] in
            if let pickup { self?.finish(.success(pickup)) }
            else { self?.finish(.failure(LioTaxiFailure.locationDenied)) }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: any Error) {
        Task { @MainActor [weak self] in self?.finish(.failure(LioTaxiFailure.locationDenied)) }
    }

    private func requestIfAuthorized() {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            guard timeout == nil else { return }
            timeout = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .seconds(12)) } catch { return }
                self?.finish(.failure(LioTaxiFailure.locationDenied))
            }
            manager.requestLocation()
        default:
            finish(.failure(LioTaxiFailure.locationDenied))
        }
    }

    private func finish(_ result: Result<LioTaxiPlace, any Error>) {
        guard let pending else { return }
        self.pending = nil
        timeout?.cancel()
        timeout = nil
        manager.stopUpdatingLocation()
        pending.resume(with: result)
    }
}
#endif
