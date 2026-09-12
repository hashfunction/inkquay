// Copyright 2026 Trieflow LLC. MIT. Native capture surfaces only.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
namespace ScriblarkMarketing {
 public sealed class Surface {
  public long Handle, Owner; public uint Pid, Dpi;
  public string Title, Class; public bool Visible, Enabled, Maximized;
  public int[] Bounds;
 }
 public static class Frame {
  [StructLayout(LayoutKind.Sequential)] struct Rect {public int Left,Top,Right,Bottom;}
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h,StringBuilder t,int n);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder t,int n);
  [DllImport("user32.dll",SetLastError=true)] static extern bool GetWindowRect(IntPtr h,out Rect r);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h,uint flag);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr h,int state);
  public static long Foreground(){return GetForegroundWindow().ToInt64();}
  public static Surface Observe(long handle){
   IntPtr h=(IntPtr)handle;uint pid;Rect r;
   if(h==IntPtr.Zero || GetWindowThreadProcessId(h,out pid)==0 || !GetWindowRect(h,out r))throw new Win32Exception();
   var title=new StringBuilder(1024);var cls=new StringBuilder(256);GetWindowText(h,title,title.Capacity);GetClassName(h,cls,cls.Capacity);
   return new Surface{Handle=handle,Owner=GetWindow(h,4).ToInt64(),Pid=pid,Title=title.ToString(),Class=cls.ToString(),
    Visible=IsWindowVisible(h),Enabled=IsWindowEnabled(h),Maximized=IsZoomed(h),Dpi=GetDpiForWindow(h),Bounds=new[]{r.Left,r.Top,r.Right-r.Left,r.Bottom-r.Top}};
  }
  public static void Require(Surface s,int pid,long main,string title,bool dialog){
   if(s.Pid!=pid || !s.Visible || !s.Enabled || s.Title!=title || s.Class!="gdkWindowToplevel" || s.Bounds.Length!=4 || s.Bounds[2]<200 || s.Bounds[3]<100 ||
       (dialog ? s.Handle==main || s.Owner!=main : s.Handle!=main))throw new InvalidOperationException("Capture input surface ownership changed");
  }
  public static void Focus(long handle,int pid,long main,string title,bool dialog){
   Require(Observe(handle),pid,main,title,dialog);
   SetForegroundWindow((IntPtr)handle);
   System.Threading.Thread.Sleep(150);
   Require(Observe(handle),pid,main,title,dialog);
   if(Foreground()!=handle)throw new InvalidOperationException("Owned capture input is not foreground");
  }
  public static void Maximize(long handle,int pid,string title){
   Require(Observe(handle),pid,handle,title,false);
   ShowWindowAsync((IntPtr)handle,3);
  }
 }
}
