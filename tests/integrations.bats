#!/usr/bin/env bats
##
# These are helper variables and functions written in Bash. It's like writing in your Terminal!
# Feel free to optimize these, or even run them in your own Terminal.
#

rootDir=$(pwd)
fixturesDir=${rootDir}/examples
testDir=''

debugger() {
    echo "--- STATUS ---"
    if [ $status -eq 0 ]
    then
        echo "Successful Status Code ($status)"
    else
        echo "Failed Status Code ($status)"
    fi
    echo "--- OUTPUT ---"
    printf '%s\n' "${lines[@]}"
    echo "--------------"
    echo "--- CONFIG ---"
    cat mkdocs.yml
    echo "--------------"
    echo "--- FILES ----"
    tree .
    echo "--------------"
}

assertGen() {
    if [ -f mkdocs-test.yml ]
    then
        cp mkdocs-test.yml mkdocs.yml
    fi
    run mkdocs build --verbose
    debugger
    [ "$status" -eq 0 ]
}

assertFileExists() {
    run cat $1
    [ "$status" -eq 0 ]
}

assertFileNotExists() {
    run cat $1
    [ "$status" -ne 0 ]
}

assertValidSite() {
    assertFileExists site/index.html
}

assertEmptySite() {
    assertFileNotExists site/index.html
}

assertServeSuccess() {
    run pgrep -x mkdocs
    debugger
    [ ! -z "$status" ]
}

assertParGrep() {
    cat site/$1/index.html | \
        awk '/<div class="col-md-9" role="main">/,/<footer class="col-md-12">/' | \
        sed '1d; $d'  | head -n -3 > site/$1.grepout
    echo "--------------"
    echo "-_---File-----"
    echo `pwd`/site/$1/index.html
    echo "-----Grep results-----"
    run diff --ignore-blank-lines --ignore-all-space $1.grepout site/$1.grepout
    echo "-----Output-----"
    cat site/$1.grepout
    echo "--------------"
    [ "$status" -eq 0 ]
}

check_site_name() {
    site_name=$(cat mkdocs.yml | sed -n 's/site_name: \(.*\)/\1/p')
    directory_name=${PWD##*/}
    echo "mkdocs site_name: $site_name, directory: $directory_name"
    [ "$site_name" == "$directory_name" ]
}

##
# These are special life cycle methods for Bats (Bash automated testing).
# setup() is ran before every test, teardown() is ran after every test.
#

teardown() {
    echo "Cleaning ${testDir}"
    rm -rf ${testDir}/site/
    rm -f ${testDir}/mkdocs.yml
    if [ -f "${testDir}/clean.sh" ]; then
        ${testDir}/clean.sh
    fi
}

##
# Test suites.
#

@test "build an empty mkdocs site with minimal configuration" {
    testDir=${fixturesDir}/ok-empty
    cd ${testDir}
    assertGen
    assertEmptySite
}

@test "build an empty mkdocs site with configuration" {
    testDir=${fixturesDir}/ok-mkdocs-config
    cd ${testDir}
    assertGen
    assertEmptySite
}
