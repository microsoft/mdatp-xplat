import 'package:flutter/material.dart';

void main() => runApp(const HelloDefenderApp());

class HelloDefenderApp extends StatelessWidget {
  const HelloDefenderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Hello Defender',
      home: Scaffold(
        body: Center(child: Text('Hello, Defender — from Flutter on macOS!')),
      ),
    );
  }
}
