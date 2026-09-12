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
    public sealed class InputState {
        public long MainHandle, ForegroundHandle, FocusHandle, FocusRoot, MenuOwner;
        public uint ProcessId, ThreadId, ForegroundProcessId, FocusProcessId, GuiFlags;
        public bool AltDown, ControlDown, ShiftDown, WindowsKeyDown;
        public long[] ForegroundOwnerChain;
        public Window[] Windows;
    }
    public sealed class ExportKey {
        public ushort VirtualKey;
        public bool KeyUp;
        public ExportKey(ushort key, bool up) { VirtualKey=key; KeyUp=up; }
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
        [StructLayout(LayoutKind.Sequential)] private struct GuiThreadInfo {
            public uint Size, Flags;
            public IntPtr Active, Focus, Capture, MenuOwner, MoveSize, Caret;
            public Rect CaretRect;
        }
        [DllImport("user32.dll", SetLastError=true)] private static extern bool GetGUIThreadInfo(uint threadId, ref GuiThreadInfo info);
        [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
        [DllImport("user32.dll")] private static extern short GetAsyncKeyState(int key);
        [StructLayout(LayoutKind.Sequential)] private struct KeyboardInput {
            public ushort Key, Scan; public uint Flags, Time; public UIntPtr Extra;
        }
        [StructLayout(LayoutKind.Sequential)] private struct MouseInput {
            public int X, Y; public uint Data, Flags, Time; public UIntPtr Extra;
        }
        [StructLayout(LayoutKind.Explicit)] private struct InputUnion {
            [FieldOffset(0)] public KeyboardInput Keyboard;
            [FieldOffset(0)] public MouseInput Mouse;
        }
        [StructLayout(LayoutKind.Sequential)] private struct Input { public uint Type; public InputUnion Data; }
        [DllImport("user32.dll", SetLastError=true)] private static extern uint SendInput(uint count, Input[] inputs, int size);
        public static InputState InspectInput(IntPtr main, int expectedPid) {
            uint pid;
            uint thread = GetWindowThreadProcessId(main, out pid);
            if (main == IntPtr.Zero || thread == 0 || pid != expectedPid)
                throw new InvalidOperationException("Retained main HWND no longer identifies the owned process");
            var info = new GuiThreadInfo {Size=(uint)Marshal.SizeOf(typeof(GuiThreadInfo))};
            if (!GetGUIThreadInfo(thread, ref info)) throw new Win32Exception();
            IntPtr foreground = GetForegroundWindow();
            uint foregroundPid, focusPid;
            GetWindowThreadProcessId(foreground, out foregroundPid);
            GetWindowThreadProcessId(info.Focus, out focusPid);
            var chain = new List<long>();
            IntPtr owner = foreground;
            while (owner != IntPtr.Zero && chain.Count < 16) {
                uint ownerPid; GetWindowThreadProcessId(owner, out ownerPid);
                if (ownerPid != expectedPid) break;
                if (chain.Contains(owner.ToInt64())) throw new InvalidOperationException("Cyclic foreground owner chain");
                chain.Add(owner.ToInt64());
                owner = GetWindow(owner, 4);
            }
            if (owner != IntPtr.Zero && chain.Count == 16) throw new InvalidOperationException("Foreground owner chain exceeds bound");
            return new InputState {MainHandle=main.ToInt64(), ProcessId=pid, ThreadId=thread,
                ForegroundHandle=foreground.ToInt64(), ForegroundProcessId=foregroundPid,
                FocusHandle=info.Focus.ToInt64(), FocusRoot=GetAncestor(info.Focus,2).ToInt64(), FocusProcessId=focusPid,
                MenuOwner=info.MenuOwner.ToInt64(), GuiFlags=info.Flags,
                AltDown=(GetAsyncKeyState(0x12)&0x8000)!=0, ControlDown=(GetAsyncKeyState(0x11)&0x8000)!=0,
                ShiftDown=(GetAsyncKeyState(0x10)&0x8000)!=0,
                WindowsKeyDown=(GetAsyncKeyState(0x5b)&0x8000)!=0 || (GetAsyncKeyState(0x5c)&0x8000)!=0,
                ForegroundOwnerChain=chain.ToArray(), Windows=Windows(expectedPid)};
        }
        public static ExportKey[] PlanExportKeys(InputState state, string title, string mnemonic) {
            AssertExportInput(state,title);
            if(state.AltDown || state.ControlDown || state.ShiftDown || state.WindowsKeyDown)
                throw new InvalidOperationException("Export input has an already-held modifier; preserving it");
            int menus=0;
            foreach(var window in state.Windows) {
                if(window.Handle==state.MainHandle)continue;
                if(window.ClassName!="gdkWindowTemp" || window.Owner!=state.MainHandle ||
                    window.ProcessId!=state.ProcessId || !window.Visible || !window.Enabled ||
                    window.Title!="com.trieflow.inkquay" || window.Width<200 || window.Height<150)
                    throw new InvalidOperationException("Unexpected or unowned export popup");
                menus++;
            }
            if(mnemonic=="%f" && menus==0)
                return new[] {new ExportKey(0x12,false),new ExportKey(0x46,false),new ExportKey(0x46,true),new ExportKey(0x12,true)};
            if(mnemonic=="e" && menus==1)
                return new[] {new ExportKey(0x45,false),new ExportKey(0x45,true)};
            throw new InvalidOperationException("Export mnemonic requires its exact observed menu state");
        }
        // One SendInput call inserts the complete native chord in order. This
        // avoids SendKeys' opaque cross-call keyboard-state handling. It does
        // not prove GTK handled the chord; the following owned dialog must open.
        private static int EmitExportKeys(ExportKey[] keys) {
            var inputs=new Input[keys.Length];
            for(int i=0;i<keys.Length;i++) {
                inputs[i].Type=1;
                inputs[i].Data.Keyboard=new KeyboardInput {Key=keys[i].VirtualKey,Flags=keys[i].KeyUp?2u:0u};
            }
            uint sent=SendInput((uint)inputs.Length,inputs,Marshal.SizeOf(typeof(Input)));
            if(sent!=inputs.Length) {
                int error=Marshal.GetLastWin32Error();
                // Release only keys whose down event was actually inserted and
                // whose matching up was not. Never repeat an action key-down.
                var held=new List<ushort>();
                for(int i=0;i<Math.Min((int)sent,keys.Length);i++) {
                    if(keys[i].KeyUp)held.Remove(keys[i].VirtualKey);else held.Add(keys[i].VirtualKey);
                }
                var releases=new Input[held.Count];
                for(int i=0;i<held.Count;i++) { releases[i].Type=1; releases[i].Data.Keyboard=new KeyboardInput {Key=held[held.Count-1-i],Flags=2}; }
                uint released=releases.Length==0?0:SendInput((uint)releases.Length,releases,Marshal.SizeOf(typeof(Input)));
                throw new InvalidOperationException("Native export chord insertion incomplete: "+sent+"/"+inputs.Length+
                    "; error="+error+"; cleanup key-up="+released+"/"+releases.Length);
            }
            return (int)sent;
        }
        public static int SendExportKeys(IntPtr main,int expectedPid,string title,string mnemonic) {
            var state=InspectInput(main,expectedPid);
            return EmitExportKeys(PlanExportKeys(state,title,mnemonic));
        }
        // Pure policy over an actual freshly observed state. The Windows caller
        // reacquires it immediately before each send and never refocuses a menu.
        public static void AssertExportInput(InputState state, string expectedTitle) {
            if (state == null || state.Windows == null || state.MainHandle == 0 || state.ProcessId == 0)
                throw new InvalidOperationException("Missing owned export input state");
            Window main = null, popup = null; int mainCount=0, popupCount=0;
            foreach (Window window in state.Windows) {
                if (window.Handle == state.MainHandle) {main=window; mainCount++;}
                if (window.Handle == state.ForegroundHandle) {popup=window; popupCount++;}
            }
            if (mainCount != 1 || main.ProcessId != state.ProcessId || !main.Visible || !main.Enabled ||
                main.ClassName != "gdkWindowToplevel" || main.Title != expectedTitle)
                throw new InvalidOperationException("Owned export main window changed or is disabled");
            if (state.ForegroundProcessId != state.ProcessId || state.FocusProcessId != state.ProcessId || state.FocusHandle == 0)
                throw new InvalidOperationException("Export foreground/focus is not owned");
            if (state.ForegroundHandle == state.MainHandle) {
                if (state.FocusRoot != state.MainHandle) throw new InvalidOperationException("Main-window export focus changed");
                return;
            }
            if (popupCount != 1 || popup.ProcessId != state.ProcessId || !popup.Visible || !popup.Enabled ||
                popup.ClassName != "gdkWindowTemp" || state.ForegroundOwnerChain == null ||
                Array.IndexOf(state.ForegroundOwnerChain,state.MainHandle) < 1 || state.ForegroundOwnerChain[0] != popup.Handle ||
                popup.Owner != state.ForegroundOwnerChain[1] ||
                (state.FocusRoot != state.MainHandle && state.FocusRoot != popup.Handle))
                throw new InvalidOperationException("Export foreground is not the observed owned GTK popup");
        }
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
