// Copyright 2026 Trieflow LLC. MIT. External qualification observer only.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
namespace InkQuayWorkflow {
    public sealed class Window {
        public long Handle, Owner;
        public uint ProcessId;
        public string Title, ClassName;
        public bool Visible, Enabled;
        public int X, Y, Width, Height;
    }
    public static class Native {
        private delegate bool Callback(IntPtr hwnd, IntPtr data);
        [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll", SetLastError=true)] private static extern bool EnumWindows(Callback cb, IntPtr data);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr hwnd);
        [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr hwnd, uint command);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int length);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder text, int length);
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
        [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hwnd);
        [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr hwnd, int command);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        public static Window[] Windows(int processId) {
            var result = new List<Window>();
            Exception failure = null;
            Callback callback = (hwnd, unused) => {
                try {
                    uint pid; GetWindowThreadProcessId(hwnd, out pid);
                    if (pid != processId || !IsWindowVisible(hwnd)) return true;
                    if (result.Count >= 100) throw new InvalidOperationException("Native window collection exceeded bound");
                    var title = new StringBuilder(4096); var name = new StringBuilder(256); Rect r;
                    if (GetWindowText(hwnd,title,title.Capacity) >= title.Capacity-1) throw new InvalidOperationException("Native title exceeded bound");
                    GetClassName(hwnd,name,name.Capacity);
                    if (!GetWindowRect(hwnd,out r)) throw new Win32Exception();
                    result.Add(new Window {Handle=hwnd.ToInt64(),Owner=GetWindow(hwnd,4).ToInt64(),ProcessId=pid,
                        Title=title.ToString(),ClassName=name.ToString(),Visible=true,Enabled=IsWindowEnabled(hwnd),
                        X=r.Left,Y=r.Top,Width=r.Right-r.Left,Height=r.Bottom-r.Top});
                    return true;
                } catch(Exception error) { failure=error; return false; }
            };
            bool ok=EnumWindows(callback,IntPtr.Zero);
            if (failure != null) throw failure;
            if (!ok) throw new Win32Exception();
            return result.ToArray();
        }
        public static void Focus(IntPtr handle,int expectedPid) {
            uint pid;
            if (handle==IntPtr.Zero || GetWindowThreadProcessId(handle,out pid)==0 || pid!=expectedPid || !IsWindowVisible(handle) || !IsWindowEnabled(handle))
                throw new InvalidOperationException("Input target is not the exact enabled owned native window");
            ShowWindow(handle,9); SetForegroundWindow(handle);
            System.Threading.Thread.Sleep(150);
            if (GetForegroundWindow()!=handle || GetWindowThreadProcessId(handle,out pid)==0 || pid!=expectedPid)
                throw new InvalidOperationException("Exact owned input window is not foreground");
        }
    }
}
