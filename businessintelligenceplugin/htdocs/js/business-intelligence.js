$(document).ready(function() {

/* -- - - - - - - - - - - - - - - 
  2. HTML MANIPULATION ON PAGE LOAD
 - - - - - - - - - - - - - - - */

  $("#content").find("h2").addAnchor(_("Link to this section"));

  $('.toggle-parameters-form').click(function(e) {
    $("i", this).toggleClass("icon-resize-full icon-resize-small");
    $(this).parent().parent().find('.parameters-form').toggle('slow');
  });

/* -- - - - - - - - - - - - - - - 
  2. EXECUTING TRANSFORMATIONS/JOBS AND SHOWING PROGESS IN UI
 - - - - - - - - - - - - - - - */

  var executions = 0;
  var executions_loading = false;
  function loadExecutions(specific_elem) {
    executions ++;
    executions_loading = true;
    var results_tables = specific_elem ? $("table", specific_elem) : $(".results-table");
    $(results_tables).each(function(i) {
      var table = $(this);
      var result_url = table.attr("data-url") + "?_=" + (new Date().getTime());
      // Load table's contents from URL
      $.ajax({
        url: result_url,
        success: function(data) {
          // Put results in DOM (hidden)
          var updated_contents = $("#ajax-results").html(data);
          // Check revision numbers against one another, update if different
          if($("td.rev", updated_contents).html() != $("td.rev", table).html()) {
            $("tbody", table).html(updated_contents.html());
            if(executions != 1) {
              $("tbody tr td", table).effect({
                duration: 2000,
                effect: "highlight",
                color: "#DFEEFD"
              });
            }
            $("tr td:first-child", table).remove();
            // If we've specified a transform object, clear the timeout and set success status
            if(specific_elem) {
              clearTimeout(specific_elem.data("timeout"));
              specific_elem.data("n", 0);
              $(".execute-actions .btn", specific_elem).removeClass("disabled");
              $(".execute-actions .btn:first", specific_elem).html("<i class='icon-bolt'></i> Execute ");
            }

          }
          if((i + 1) == results_tables.length) executions_loading = false;
        },
        error: function() {
          if((i + 1) == results_tables.length) executions_loading = false;
        }
      });
    });
  };

  // populate the initial file archive HTML
  loadExecutions();

  // global scope array to hold transform objects
  var running_transforms = [];

  // check every 2 seconds the status of each recently executed transform/job
  // only send an AJAX request if the running_transformations array is not empty
  var progressHandler = setInterval(function(){
    if ( running_transforms.length > 0 ) {

      var running_uuids = [];
      for (var i=0; i < running_transforms.length ; i++) {
        running_uuids.push(running_transforms[i]['id']);
      }

      $.ajax({
        type: 'GET',
        data: {
          'action': 'check_status',
          'uuid': JSON.stringify(running_uuids)
        },
        url: window.tracBaseUrl + 'businessintelligence',
        success: function(data) {
          // loop through the JSON response and check the status
          for (var index=0; index < data.length; index++) {
            // update the running_transform objects
            if (data[index]['status'] == 'success') {
              for (var i=0; i < running_transforms.length; i++) {
                if (running_transforms[i]['id'] == data[index]['id']) {
                  var completed_trans = running_transforms[i];
                  updateUserInterface(completed_trans['group_label'], completed_trans['btn_handler'], 'alert-success',
                    "Successfully executed '" + completed_trans['name'] + "' transformation.");

                  // now we also update the inline file browser div
                  timeout_browser = setInterval(function() { if(!executions_loading) loadExecutions(); }, 2000);

                  // and we remove this transform/job from running_transforms array
                  removeTransformation(completed_trans['name']);
                }
              }
            }
            else if (data[index]['status'] == 'error') {
              for (var i=0; i < running_transforms.length; i++) {
                if (running_transforms[i]['id'] == data[index]['id']) {
                  var failed_trans = running_transforms[i];
                  updateUserInterface(failed_trans['group_label'], failed_trans['btn_handler'], 'alert-danger',
                    "Failed to execute '" + failed_trans['name'] + "' transformation.");

                  // and we remove this transform/job from running_transforms array
                  removeTransformation(failed_trans['name']);
                }
              }
            }
          }
        }
      });
    }
  }, 2000)

  function removeTransformation(name) {
    $.each(running_transforms, function(i) {
      if(running_transforms[i]['name'] == name) {
        running_transforms.splice(i, 1);
        return; 
      }
    });
  }

  function updateUserInterface(group_label, btn_handler, alert, message) {
    /**
    Update the UI to reflect the completion or failure of a transformation.
    **/

    // update the UI (change button styling, add a alert message)
    group_label.removeClass("btn-warning disabled").addClass('btn-success').html("<i class='icon-bolt'></i> Execute");
    $(".btn", btn_handler).removeClass("btn-warning disabled").addClass("btn-success");
    $("#content").prepend('<div class="cf alert ' + alert + ' alert-dismissable individual">\
                            <i class="alert-icon icon-info-sign"></i>\
                            <div style="display:inline">' + message + '</div>\
                            <button type="button" class="close btn btn-mini" data-dismiss="alert">\
                              <i class="icon-remove"></i>\
                            </button>\
                          </div>')
  }

  // listen to clicks on an exectute button
  $(".execute-actions a[data-action]").click(function() {
    transform_name = $(this).closest(".execute-actions").attr("data-transform");
    $transform_wrapper = $("#transform-" + transform_name);
    $execute_btn_handler = $(".execute-actions", $transform_wrapper);
    $group_label = $(".group-label", $execute_btn_handler);

    if($(".btn.disabled", $execute_btn_handler).length == 0) {
      // Set our form values given the execution request
      $("#exec-action").val($(this).attr("data-action"));
      $("#exec-transform").val(transform_name);
      $("#exec-form input.bi-parameter").remove();
      $transform_wrapper.find("input.bi-parameter").clone().appendTo($("#exec-form"));
      // Change the button state to loading
      $group_label.html("<i class='icon-spin icon-spinner'></i> Executing...");
      $group_label.removeClass("btn-success").addClass("btn-warning");
      $group_label.next().removeClass("btn-success").addClass("btn-warning");
      $(".btn", $execute_btn_handler).addClass("disabled");

      // If our request is not to async
      if($("#exec-action").val() != "execute_download") {
        $("#exec-form").ajaxSubmit({
          url: window.tracBaseUrl + 'businessintelligence',
          success: function(data) {
            running_transforms.push({
              id: data['transform_id'],
              status: 'executed',
              name: transform_name,
              wrapper: $transform_wrapper,
              btn_handler: $execute_btn_handler,
              group_label: $group_label
            });
          },
          error: function() {
            // TODO something better than a alert box
            alert("Unable to execute!")
          }
        });
      }
      else {
        // we have this set at an arbitary 30 seconds - maybe we can 
        // be cleverer than that? why don't we request via $.ajax() and send 
        // a response so we know for sure when to change the icons back?
        setTimeout(function() {
          $(".btn", $execute_btn_handler).removeClass("disabled");
          $group_label.removeClass("disabled").addClass("btn-success").html("<i class='icon-bolt'></i> Execute");
          $group_label.next().addClass("btn-success");
        }, 30000);
        $("#exec-form").submit();
      }
    }
    $execute_btn_handler.removeClass("open");
    return false;
  });

/* -- - - - - - - - - - - - - - - 
  3. RUNNING TRANSFORM DIALOG
 - - - - - - - - - - - - - - - */
  $("#dialogrunning").dialog({
    autoOpen: false,
    width: 800,
    modal: true,
    title: "Running Transformations"
  });

  $("#runningbutton").click(function(){
    // get the data to populate the dialog
    $.ajax({
      method: 'GET',
      data: {
        'action': 'check_status',
        'uuid': JSON.stringify(['all'])
      },
      url: window.tracBaseUrl + 'businessintelligence',
      success: function(data) {
        // clear the rows in current table
        $("#runningtable > tbody").html("");
        // add new rows
        $('#runningtable').append('<tr><th>UUID</th><th>Started</th><th>Running</th></tr>');
        for (var i=0; i < data.length; i++) {
          $('#runningtable').append('<tr><td>' + data[i]['id'] + '</td><td>' + new Date (data[i]['started']) + '</td><td><i class="icon-spin icon-spinner"></i></td></tr>');
        }
      },
      error: function(data) {
        $("#dialogrunning").html("<p>There was an error. Please try again.</p>");
      }
    });
    // open the running transform dialog
    $("#dialogrunning").dialog('open');
    return false;
  });

/* -- - - - - - - - - - - - - - - 
  4. OTHER DIALOGS FOR BUSINESS INTELLIGENCE PAGE
 - - - - - - - - - - - - - - - */

  $("#bi-integration-url-dialog").dialog({
    autoOpen: false,
    width: 500,
    modal: true,
    title: "Report GET URL"
  });
  $("#content .get-url-btn").click(function(){
    example_url = this.href + "&" + $(this).parent().parent().find("input.bi-parameter").serialize();
    $("#bi-integration-url-placeholder").attr('href', example_url);
    $("#bi-integration-url-placeholder").text(example_url);
    $("#bi-integration-url-dialog").dialog('open');
    return false;
  });

  $("#dialogupload").dialog({autoOpen: false,
    width: 400,
    modal: true,
    title:"Upload Transformations"
  });
  $("#uploadbutton").click(function(){
    $("#dialogupload").dialog('open');
    return false;
  });

  $("#dialogschedule").dialog({
    autoOpen: false,
    width: 400,
    modal: true,
    title: "Schedule Transformations"
  });
  $("#schedulebutton").click(function(){
    $("#dialogschedule").dialog('open');
    return false;
  });

});