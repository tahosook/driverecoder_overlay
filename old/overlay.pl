#!/usr/bin/perl

use strict;
use warnings;

# 引数からファイル名を取得する
my $arg = $ARGV[0];

if(-d $arg){
    opendir my $dh, $arg or die "Cannot open directory $arg: $!";
    my @files = grep { /\.MOV$/ } readdir $dh;
    closedir $dh;

    foreach my $file (@files) {
        ffmpeg("$arg/$file") if($file !~ /R.MOV$/);
    }
}elsif(-f $arg){
    ffmpeg($arg);
}else{ 
    print "Usage: $0 <filename>";
    exit;
}

sub ffmpeg($)
{
    my($filename)=@_;

    # 拡張子が .MOV の場合は除去する
    $filename =~ s/\.MOV$//i;

    # 前方と後方の動画のファイル名を生成する
    my $front_file = "$filename.MOV";
    my $rear_file = "$filename" . "R.MOV";
    
    # ffmpegコマンドを生成する
    my $cmd = "ffmpeg -i $front_file -i $rear_file ".
        '-filter_complex "[1:v]scale=iw/2.5:ih/2.5[v1];[0:v][v1]overlay=W-w-20:H-h-70,setpts=0.05*PTS[v];[0:a]anlmdn[a];[a]atempo=20[b]" -map "[v]" -map "[b]" -c:v libx264 -preset veryfast -crf 23'.
        " $filename.mp4";
        
    # コマンドを実行する
    system($cmd);
    #print($cmd);
}
