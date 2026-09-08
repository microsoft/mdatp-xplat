import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("Hello Defender")
                .font(.largeTitle)
                .fontWeight(.semibold)
                .accessibilityIdentifier("helloTitle")
            Text("iOS Simulator Performance Profile Demo")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
